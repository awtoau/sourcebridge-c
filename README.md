# Sourcebridge C frontend pack

This pack extracts compiler-grounded C facts for Sourcebridge. It starts with
the public `c-testsuite` `single-exec` corpus: each upstream case is one C
program with an expected combined stdout/stderr result.

The pack is deliberately small. It validates an upstream case with a selected
C compiler, records a whole-tree corpus manifest, and extracts a constrained
fact model from Clang's JSON AST. The scalar expression subset includes
parenthesized expressions, integer literals, and binary `+`, `-`, `*`, and `/`
operators. Unsupported syntax fails explicitly; it does not produce target
code or infer a rule.

## Relationship to linux-rs

This pack does not replace or import linux-rs's current translation pipeline.
That pipeline uses c2rust to produce raw Rust, then applies Linux-specific
rule checks and kernel integration validation:

```text
Linux C + compile_commands.json
  -> c2rust
  -> raw Rust
  -> Linux rules and integration checks
  -> Rust compiler, Clippy, QEMU, and KUnit evidence
```

The Clang AST fingerprinting code identified during migration is an auxiliary
Linux-rs analysis tool, not its translator. This pack currently stops at
compiler-grounded C facts:

```text
c-testsuite C case
  -> Clang AST
  -> Sourcebridge C facts and source-validation evidence
```

A future profile may adapt the c2rust pipeline as a selected backend, but no
such adapter exists yet. No existing Linux rule has been transferred to this
pack.

## Corpus and variant

- Corpus: `https://github.com/c-testsuite/c-testsuite.git`
- Pinned revision: `5c7275656d751de0e68b2d340a95b5681858ed07`
- Initial variant: Clang 22.1.8, `x86_64-redhat-linux-gnu`, ISO C11

Bootstrap a separate corpus checkout:

```text
python3 tools/bootstrap_c_testsuite.py --destination ../c-testsuite
```

Record its complete source-tree manifest:

```text
python3 tools/record_c_testsuite_manifest.py \
  --corpus-root ../c-testsuite \
  --output evidence/c-testsuite-manifest.json
```

Validate an upstream case and extract its facts:

```text
python3 tools/validate_c_testsuite_case.py \
  --corpus-root ../c-testsuite \
  --case tests/single-exec/00002.c

python3 tools/extract_c_test_fact.py \
  --corpus-root ../c-testsuite \
  --source tests/single-exec/00002.c \
  --variant variants/clang-22.1.8-x86_64-linux-c11.json \
  --output evidence/00002.clang.facts.json
```

Run the native C-to-Rust proof against that same upstream case:

```text
python3 tools/validate_c_scalar_rust.py \
  --corpus-root ../c-testsuite \
  --rust-pack ../sourcebridge-rust
```

## Rule migration boundary

[`sourcebridge-linux`](https://github.com/awtoau/sourcebridge-linux) preserves
the completed Linux conversion work and is evidence for this pack. Its rules
are not automatically copied or applied. A reusable C rule must be classified
as language-generic, given positive and negative cases, and pass the selected
source and target validation profile before promotion. Kernel APIs, Linux build
configuration, architecture assumptions, and runtime shims remain in the Linux
corpus pack.

The local-model baseline is optional and cannot propose or change a rule. It
measures whether a bounded queue of already-supported compiler facts correctly
returns `no_change_needed`, rather than spending subsequent conversion work on
known coverage. Build the facts from a temporary corpus checkout, then run:

```text
python3 tools/run_c_fact_baseline_batch.py --facts-dir tmp/ollama-c-facts
```

The worker is local-only, digest-pinned, preserves raw staged/rejected
responses with their fact provenance, and unloads after the one-language batch.
Use unsupported compiler fact shapes for proposal work; this baseline exists to
measure unnecessary-request avoidance.

The audited Linux-rs reuse boundary is recorded and checked with:

```text
python3 tools/verify_linux_migration_inventory.py
```
