# Evidence bundles

Both benchmarks run on these files. They are synthetic: no real agent, host or credential is behind any of them.

| file | holds |
|---|---|
| `bundles/*.json` | 20 evidence bundles, one per synthetic agent. This is the input an ASP scorer sees. |
| `scenarios.jsonl` | The facts each bundle was generated from, such as whether it runs as root, its mounts and its credentials. No model ever sees these. Risk detection uses them to check whether a score follows a fact the bundle shows. |

The alignment benchmark's later snapshots are derived from these bundles and live in [`../alignment_detection/data`](../alignment_detection/data).

## Where they come from

- **Source:** copied from `asp-datagen`, pilot 1 (commit `b4ce3db`, generated on 2026-09-24 with seed 20260924).
- **Facts:** every fact that bears on risk was sampled by code. That covers the user, privileged mode, capabilities, mounts, credentials and their provenance, and every `status`, `reason`, `tier` and `authored_by`.
- **Surface text:** agent names, tool names, hostnames and skill text were written per bundle by open-weight models (`qwen2.5:7b` for 15 bundles, `mistral-nemo` for 5).
- **Fixed text:** the `method` and `note` strings, mount paths and credential shapes are fixed templates.
- **Collection context:** each bundle follows a collection context from A to E, which sets which sources the scanner reached. So some attributes are `BLIND` or `PARTIAL`, as they would be in a real scan.

## Format

- **Top level:** each bundle is `bundle_version` 1 and carries its `bundle_id`, `collected_at` and `inputs_attempted`, plus 26 `attributes`.
- **Attributes:** each attribute has:
  - `status`: `ANSWERED`, `PARTIAL`, `TEMPLATED`, `ABSENT`, `BLIND` or `FAILED`;
  - `tier`: `observed`, `declared` or `interrogated`;
  - `value`: when the scanner could see it;
  - optional `reason`, `authored_by`, `method` and `note`.

| attributes | |
|---|---|
| identity | `image_digest`, `harness_identity`, `framework_identity`, `deployment`, `user`, `workdir` |
| model | `model_name`, `inference_endpoint` |
| tools | `mcp_servers_declared`, `mcp_servers_observed`, `tool_names`, `tool_capability_envelope`, `tool_allow_deny`, `approval_policy` |
| egress | `declared_destinations`, `observed_destinations`, `undeclared_destinations`, `sandbox_network_policy` |
| secrets | `credential_inventory`, `credential_provenance`, `in_layer_deleted_secrets` |
| container | `mounts`, `permissions` |
| content | `system_prompt_present`, `system_prompt_text`, `skills_inventory` |

## Not included

Rail Center's three test-vector bundles are not copied here, because this repository is public. The earlier `risk_detection/asp_score.py` experiment used them, and it reads them from a Rail Center checkout instead.
