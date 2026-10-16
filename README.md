# Sourcebridge C frontend pack

This pack extracts compiler-grounded C facts for Sourcebridge. It starts with
the public `c-testsuite` `single-exec` corpus: each upstream case is one C
program with an expected combined stdout/stderr result.

The pack is deliberately small. It validates an upstream case with a selected
C compiler, records a whole-tree corpus manifest, and extracts a constrained
fact model from Clang's JSON AST. Unsupported syntax fails explicitly; it does
not produce target code or infer a rule.

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

## Rule migration boundary

[`sourcebridge-linux`](https://github.com/awtoau/sourcebridge-linux) preserves
the completed Linux conversion work and is evidence for this pack. Its rules
are not automatically copied or applied. A reusable C rule must be classified
as language-generic, given positive and negative cases, and pass the selected
source and target validation profile before promotion. Kernel APIs, Linux build
configuration, architecture assumptions, and runtime shims remain in the Linux
corpus pack.

No local-model request is part of this pack's workflow.

