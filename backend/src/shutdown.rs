use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::time::Instant;

/// Terminal status of the shutdown process.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ShutdownTerminalStatus {
    /// Shutdown has not started yet.
    NotStarted,
    /// Shutdown is in progress, draining connections.
    Draining,
    /// Shutdown completed gracefully within the grace period.
    Completed,
    /// Shutdown timed out; some connections may have been force-closed.
    TimedOut,
}

/// Snapshot of the backend shutdown state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShutdownMetricsSnapshot {
    /// Whether shutdown has been initiated.
    pub shutdown_started: bool,
    /// Configured grace period in seconds.
    pub grace_period_seconds: u64,
    /// Seconds elapsed since shutdown began.
    pub elapsed_seconds: f64,
    /// Terminal status of the shutdown.
    pub terminal_status: ShutdownTerminalStatus,
}

/// Tracks the state of a graceful shutdown.
pub struct ShutdownMetrics {
    started: AtomicBool,
    grace_period_seconds: AtomicU64,
    start_instant: std::sync::Mutex<Option<Instant>>,
    terminal: std::sync::Mutex<ShutdownTerminalStatus>,
}

impl ShutdownMetrics {
    pub fn new(grace_period_seconds: u64) -> Self {
        Self {
            started: AtomicBool::new(false),
            grace_period_seconds: AtomicU64::new(grace_period_seconds),
            start_instant: std::sync::Mutex::new(None),
            terminal: std::sync::Mutex::new(ShutdownTerminalStatus::NotStarted),
        }
    }

    /// Mark shutdown as started.
    pub fn begin_shutdown(&self) {
        self.started.store(true, Ordering::SeqCst);
        *self.start_instant.lock().unwrap() = Some(Instant::now());
        *self.terminal.lock().unwrap() = ShutdownTerminalStatus::Draining;
    }

    /// Mark shutdown as completed gracefully.
    pub fn mark_completed(&self) {
        *self.terminal.lock().unwrap() = ShutdownTerminalStatus::Completed;
    }

    /// Mark shutdown as timed out.
    pub fn mark_timed_out(&self) {
        *self.terminal.lock().unwrap() = ShutdownTerminalStatus::TimedOut;
    }

    /// Take a snapshot of the current shutdown metrics.
    pub fn snapshot(&self) -> ShutdownMetricsSnapshot {
        let started = self.started.load(Ordering::SeqCst);
        let grace = self.grace_period_seconds.load(Ordering::SeqCst);
        let elapsed = if started {
            self.start_instant
                .lock()
                .unwrap()
                .map(|t| t.elapsed().as_secs_f64())
                .unwrap_or(0.0)
        } else {
            0.0
        };
        let terminal = self.terminal.lock().unwrap().clone();
        ShutdownMetricsSnapshot {
            shutdown_started: started,
            grace_period_seconds: grace,
            elapsed_seconds: elapsed,
            terminal_status: terminal,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pre_shutdown_state() {
        let metrics = ShutdownMetrics::new(30);
        let snap = metrics.snapshot();
        assert!(!snap.shutdown_started);
        assert_eq!(snap.grace_period_seconds, 30);
        assert_eq!(snap.elapsed_seconds, 0.0);
        assert_eq!(snap.terminal_status, ShutdownTerminalStatus::NotStarted);
    }

    #[test]
    fn test_draining_state() {
        let metrics = ShutdownMetrics::new(30);
        metrics.begin_shutdown();
        let snap = metrics.snapshot();
        assert!(snap.shutdown_started);
        assert!(snap.elapsed_seconds >= 0.0);
        assert_eq!(snap.terminal_status, ShutdownTerminalStatus::Draining);
    }

    #[test]
    fn test_completed_state() {
        let metrics = ShutdownMetrics::new(30);
        metrics.begin_shutdown();
        metrics.mark_completed();
        let snap = metrics.snapshot();
        assert!(snap.shutdown_started);
        assert_eq!(snap.terminal_status, ShutdownTerminalStatus::Completed);
    }

    #[test]
    fn test_timeout_state() {
        let metrics = ShutdownMetrics::new(30);
        metrics.begin_shutdown();
        metrics.mark_timed_out();
        let snap = metrics.snapshot();
        assert!(snap.shutdown_started);
        assert_eq!(snap.terminal_status, ShutdownTerminalStatus::TimedOut);
    }
}
