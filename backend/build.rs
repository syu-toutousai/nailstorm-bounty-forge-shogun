use std::fs;
use std::path::Path;
use std::process;

fn main() {
    println!("cargo:rerun-if-changed=src/protocol/");

    let protocol_dir = Path::new("src/protocol");
    if !protocol_dir.exists() {
        return;
    }

    let mut missing = Vec::new();

    for entry in fs::read_dir(protocol_dir).expect("failed to read protocol dir") {
        let entry = entry.expect("failed to read dir entry");
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }

        let content = fs::read_to_string(&path).expect("failed to read file");
        let lines: Vec<&str> = content.lines().collect();

        for (i, line) in lines.iter().enumerate() {
            let trimmed = line.trim();
            if !trimmed.starts_with("#[derive(") {
                continue;
            }
            if !trimmed.contains("Serialize") || !trimmed.contains("Deserialize") {
                continue;
            }

            let mut has_rename_all = false;
            let mut j = i + 1;
            while j < lines.len() {
                let next = lines[j].trim();
                if next.starts_with("#[serde(") && next.contains("rename_all") {
                    has_rename_all = true;
                    break;
                }
                if next.starts_with("pub struct") || next.starts_with("pub enum") {
                    break;
                }
                if !next.starts_with("#[") && !next.starts_with("//") && !next.is_empty() {
                    break;
                }
                j += 1;
            }

            if !has_rename_all {
                let struct_line = if j < lines.len() { lines[j].trim() } else { "unknown" };
                let file_name = path.file_name().unwrap().to_string_lossy();
                missing.push(format!("{}:{}: {} (missing rename_all)", file_name, j + 1, struct_line));
            }
        }
    }

    if !missing.is_empty() {
        eprintln!("\n=== Protocol serde check FAILED ===");
        eprintln!("The following types derive Serialize/Deserialize but lack #[serde(rename_all)]:\n");
        for m in &missing {
            eprintln!("  {}", m);
        }
        eprintln!("\nAdd #[serde(rename_all = \"snake_case\")] to each type listed above.");
        eprintln!("See bounty issue for details.\n");
        process::exit(1);
    }

    println!("cargo:warning=Protocol serde check passed: all types have rename_all");
}
