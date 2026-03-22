#!/usr/bin/env python3
# test_scanner.py — run manually
from scanner import build_cross_manifest, CrossPathDuplicateFinder, StructureAnalyzer

# Test on a real directory
paths = ["/home/sigge/.openclaw/workspace/vault"]
manifest = build_cross_manifest(paths, mode="deep")
print(f"Scanned: {manifest['scan_meta']['total_files']} files")
print(f"Total size: {manifest['scan_meta']['total_size_bytes']:,} bytes")
print(f"By category: {manifest['stats']['by_category']}")
print(f"By classification: {manifest['stats']['by_classification']}")

dupes = CrossPathDuplicateFinder(manifest["files"]).find()
print(f"Duplicate groups: {dupes['stats']['total_groups']}")
print(f"  - exact: {dupes['stats']['exact_count']}")
print(f"  - likely: {dupes['stats']['likely_count']}")
print(f"  - wasted space: {dupes['stats']['total_wasted_space']:,} bytes")

struct = StructureAnalyzer(manifest, paths).analyze()
print(f"Structure issues: {len(struct['issues'])}")
for issue in struct['issues'][:5]:
    print(f"  [{issue['severity']}] {issue['type']}: {issue['message']}")
