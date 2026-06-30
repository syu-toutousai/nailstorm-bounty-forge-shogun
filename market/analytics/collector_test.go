package analytics

import (
	"testing"
)

func TestCollectorTagCardinalityUnderLimitRecordsSamples(t *testing.T) {
	collector := NewCollector().WithTagCardinalityLimit(2)

	if ok, err := collector.Record(counterSample("orders_total", "tenant", "alpha")); !ok || err != nil {
		t.Fatalf("first tag set should be recorded, got: %t, %v", ok, err)
	}
	if ok, err := collector.Record(counterSample("orders_total", "tenant", "beta")); !ok || err != nil {
		t.Fatalf("second tag set should be recorded, got: %t, %v", ok, err)
	}

	stats := collector.Stats()
	if stats.BufferedSamples != 2 {
		t.Fatalf("buffered samples = %d, want 2", stats.BufferedSamples)
	}
	if stats.Dropped != 0 || stats.DroppedTagCardinality != 0 {
		t.Fatalf("drops = %d/%d, want 0/0", stats.Dropped, stats.DroppedTagCardinality)
	}
	if got := stats.TagCardinality["orders_total"]; got != 2 {
		t.Fatalf("tag cardinality = %d, want 2", got)
	}
}

func TestCollectorTagCardinalityOverLimitDropsNewTagSet(t *testing.T) {
	collector := NewCollector().WithTagCardinalityLimit(1)

	if ok, err := collector.Record(counterSample("orders_total", "tenant", "alpha")); !ok || err != nil {
		t.Fatalf("first tag set should be recorded, got: %t, %v", ok, err)
	}
	if ok, err := collector.Record(counterSample("orders_total", "tenant", "beta")); ok || err != ErrTagCardinalityLimitExceeded {
		t.Fatalf("second unique tag set should be dropped with ErrTagCardinalityLimitExceeded, got: %t, %v", ok, err)
	}

	stats := collector.Stats()
	if stats.BufferedSamples != 1 {
		t.Fatalf("buffered samples = %d, want 1", stats.BufferedSamples)
	}
	if stats.Dropped != 1 {
		t.Fatalf("dropped = %d, want 1", stats.Dropped)
	}
	if stats.DroppedTagCardinality != 1 {
		t.Fatalf("tag-cardinality drops = %d, want 1", stats.DroppedTagCardinality)
	}
}

func TestCollectorTagCardinalityRepeatedHighCardinalityInputDropsDeterministically(t *testing.T) {
	collector := NewCollector().WithTagCardinalityLimit(1)

	if ok, err := collector.Record(counterSample("orders_total", "tenant", "alpha")); !ok || err != nil {
		t.Fatalf("first tag set should be recorded, got: %t, %v", ok, err)
	}
	for i := 0; i < 3; i++ {
		if ok, err := collector.Record(counterSample("orders_total", "tenant", "overflow")); ok || err != ErrTagCardinalityLimitExceeded {
			t.Fatalf("overflow tag set attempt %d should be dropped with ErrTagCardinalityLimitExceeded, got: %t, %v", i+1, ok, err)
		}
	}
	if ok, err := collector.Record(counterSample("orders_total", "tenant", "alpha")); !ok || err != nil {
		t.Fatalf("previously accepted tag set should still be recorded, got: %t, %v", ok, err)
	}

	stats := collector.Stats()
	if stats.BufferedSamples != 2 {
		t.Fatalf("buffered samples = %d, want 2", stats.BufferedSamples)
	}
	if stats.DroppedTagCardinality != 3 {
		t.Fatalf("tag-cardinality drops = %d, want 3", stats.DroppedTagCardinality)
	}
	if got := stats.TagCardinality["orders_total"]; got != 1 {
		t.Fatalf("tracked tag cardinality = %d, want 1", got)
	}
}

func TestCollectorTagCardinalityUsesDeterministicTagSignature(t *testing.T) {
	collector := NewCollector().WithTagCardinalityLimit(1)

	first := MetricSample{
		Name: "orders_total",
		Type: MetricTypeCounter,
		Tags: []MetricTag{{Key: "tenant", Value: "alpha"}, {Key: "region", Value: "us"}},
	}
	second := MetricSample{
		Name: "orders_total",
		Type: MetricTypeCounter,
		Tags: []MetricTag{{Key: "region", Value: "us"}, {Key: "tenant", Value: "alpha"}},
	}

	if ok, err := collector.Record(first); !ok || err != nil {
		t.Fatalf("first tag ordering should be recorded, got: %t, %v", ok, err)
	}
	if ok, err := collector.Record(second); !ok || err != nil {
		t.Fatalf("same tag set in different order should still be recorded, got: %t, %v", ok, err)
	}

	stats := collector.Stats()
	if stats.DroppedTagCardinality != 0 {
		t.Fatalf("tag-cardinality drops = %d, want 0", stats.DroppedTagCardinality)
	}
	if got := stats.TagCardinality["orders_total"]; got != 1 {
		t.Fatalf("tracked tag cardinality = %d, want 1", got)
	}
}

func TestCollectorBacklogLimitExceeded(t *testing.T) {
	collector := NewCollector()
	collector.maxBacklog = 2

	if ok, err := collector.Record(counterSample("orders_total", "tenant", "a")); !ok || err != nil {
		t.Fatalf("first should succeed, got: %t, %v", ok, err)
	}
	if ok, err := collector.Record(counterSample("orders_total", "tenant", "b")); !ok || err != nil {
		t.Fatalf("second should succeed, got: %t, %v", ok, err)
	}
	if ok, err := collector.Record(counterSample("orders_total", "tenant", "c")); ok || err != ErrBacklogLimitExceeded {
		t.Fatalf("third should fail with backlog error, got: %t, %v", ok, err)
	}
}

func counterSample(name, key, value string) MetricSample {
	return MetricSample{
		Name: name,
		Type: MetricTypeCounter,
		Tags: []MetricTag{{Key: key, Value: value}},
	}
}
