# ChessStealthPro Test Infrastructure & 4-Tier Verification Guide

## 1. Overview & Testing Philosophy

The ChessStealthPro automated test infrastructure provides comprehensive, opaque-box, multi-tier verification covering all 15 security, cryptographic, edge, and anti-tamper features across Milestones M1 through M5.

### Testing Methodology
- **Opaque-Box Requirement-Driven Testing**: Tests interact strictly through public interfaces, cryptographic verifiers, HTTP endpoints, IPC protocols, and Windows OS APIs. Internal variables or private state are not mocked away to fake test passes.
- **Progressive Testability**: Baseline features and regression paths remain verifiable throughout all phases of development.
- **Independence & Isolation**: Every test operates in a hermetically isolated execution boundary using ephemeral databases, clean environment contexts, and scoped fixtures.

---

## 2. Environment & Runtime Specifications

- **Python Runtime**: `C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe` (Python 3.14.6 x64)
- **Pytest Version**: 9.2.0 (`pluggy 1.7.0`, `anyio 4.14.2`)
- **Web & Async Frameworks**: FastAPI 0.162.0, Starlette 1.3.1, HTTPX 0.28.1
- **Cryptographic Hazmat**: `cryptography` 50.0.0 (Ed25519, SHA256, HMAC), `pycryptodome` 3.23.0
- **GUI & Display Framework**: PySide6 6.11.1 (Qt 6.11.1)
- **Node.js Edge Runtime**: Node.js v22.23.2 (`C:\Users\Windows\AppData\Local\pi-node\current\node.exe`)

---

## 3. Test Runner & Execution Commands

All commands are executed from the project root (`C:\Users\Windows\ChessStealthPro`).

### 3.1 Full Test Suite Execution (Regression + E2E Security)
```powershell
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest
```

### 3.2 Tier-Specific Test Runs
Run specific test tiers using the registered pytest markers:
```powershell
# Tier 1: Isolated Feature Coverage (Category-Partition)
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest -m tier1

# Tier 2: Boundary & Corner Cases (BVA / Extremes / Tamper Rejection)
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest -m tier2

# Tier 3: Cross-Feature Integration Chains & Pairwise Combinations
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest -m tier3

# Tier 4: Real-World Workloads & Adversary Attack Gauntlets
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest -m tier4
```

### 3.3 Master E2E Security Suite Only
```powershell
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_e2e_security.py
```

### 3.4 Unit & Component Regression Suite Only
```powershell
& "C:\Users\Windows\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/test_activation_window.py tests/test_crypto_web_keys.py tests/test_engine_dropdown.py tests/test_license_core.py tests/test_no_autolaunch_and_universal_browser.py tests/test_palette_ui.py tests/test_verify_activate.py
```

---

## 4. Fixture Architecture (`tests/conftest.py`)

Shared fixtures located in `tests/conftest.py` decouple test logic from global filesystem and process state:

| Fixture Name | Scope | Description |
|--------------|-------|-------------|
| `clean_env` | Function | Snapshots `os.environ` before test execution and restores it on teardown. |
| `isolated_db` | Function | Allocates an ephemeral SQLite database file, executes migrations (`run_migrations(seed_defaults=True)`), sets `CHESSPRO_DB_PATH`, and unlinks the file on teardown. |
| `test_client` | Function | Yields a `fastapi.testclient.TestClient` bound to the active `isolated_db`. |
| `qapp` | Session | Instantiates a headless `QApplication` instance (offscreen platform) to safely execute Qt widget tests without GUI popups. |
| `sign_webhook` | Function | Factory producing valid HMAC-SHA256 signatures for arbitrary request bodies using active test secrets. |
| `clock_controller` | Function | Monkeypatches `time.time` with a controllable monotonic clock capable of simulating advancement and rollback. |
| `cf_worker_env` | Function | Provides a mock execution context for Cloudflare Worker KV storage, environment variables, and request handling. |
| `mock_win32_api` | Function | Configurable mock for Windows OS security APIs (`IsDebuggerPresent`, `CheckRemoteDebuggerPresent`, hook inspection). |

---

## 5. Traceability Matrix (Features 1–15 Across Tiers 1–4)

| Feature # | Feature Name | Tier 1 (Feature Coverage) | Tier 2 (Boundary & Corner) | Tier 3 (Cross-Feature) | Tier 4 (Real-World Scenarios) |
|---|---|---|---|---|---|
| **F1** | Cryptographic Key Separation | `test_t1_f1_public_key_only_verification`, `test_t1_f1_initial_activation_signature`, `test_t1_f1_canonical_payload_invariance`, `test_t1_f1_offline_cache_signature`, `test_t1_f1_valid_public_key_format` | `test_t2_f1_signature_length_boundary`, `test_t2_f1_non_hex_signature`, `test_t2_f1_single_bit_payload_tamper`, `test_t2_f1_foreign_key_pair_rejected`, `test_t2_f1_missing_canonical_fields` | `test_t3_cross_payment_activation_gating` | `test_t4_adversary_attack_gauntlet` |
| **F2** | Offline Keygen Elimination | `test_t1_f2_server_authorized_key_verification`, `test_t1_f2_authoritative_db_persistence`, `test_t1_f2_high_entropy_token_generation`, `test_t1_f2_parameterized_key_lookup`, `test_t1_f2_clean_status_responses` | `test_t2_f2_legacy_offline_hmac_rejected`, `test_t2_f2_truncated_signature_collision`, `test_t2_f2_malformed_key_strings`, `test_t2_f2_revoked_key_rejection`, `test_t2_f2_sql_injection_rejection` | `test_t3_cross_offline_cache_tamper_rollback` | `test_t4_adversary_attack_gauntlet` |
| **F3** | Anti-Clock Rollback & Replay | `test_t1_f3_monotonic_high_water_progression`, `test_t1_f3_unique_nonce_generation`, `test_t1_f3_legitimate_expiration_enforcement`, `test_t1_f3_nonce_tracking_lifecycle`, `test_t1_f3_consecutive_verifications` | `test_t2_f3_clock_rollback_blocks_scale`, `test_t2_f3_nonce_replay_attack_rejected`, `test_t2_f3_future_clock_skew_expiration`, `test_t2_f3_empty_malformed_nonce_rejected`, `test_t2_f3_cache_high_water_tamper_rejected` | `test_t3_cross_free_claim_to_rollback` | `test_t4_commercial_customer_lifecycle` |
| **F4** | Webhook Signature Enforcement | `test_t1_f4_valid_signature_accepted`, `test_t1_f4_case_insensitive_signature`, `test_t1_f4_usd_lifetime_classification`, `test_t1_f4_vnd_lifetime_classification`, `test_t1_f4_monthly_plan_classification` | `test_t2_f4_mandatory_signature_missing_401`, `test_t2_f4_empty_signature_header_401`, `test_t2_f4_tampered_webhook_body_401`, `test_t2_f4_fallback_secret_rejected_401`, `test_t2_f4_malformed_payload_rejected_422` | `test_t3_cross_payment_activation_gating` | `test_t4_adversary_attack_gauntlet` |
| **F5** | Webhook Data Leakage Prevention | `test_t1_f5_webhook_response_omits_license_key`, `test_t1_f5_db_fulfillment_verified`, `test_t1_f5_first_time_idempotency_flag`, `test_t1_f5_replay_idempotency_flag`, `test_t1_f5_decoupled_fulfillment_log` | `test_t2_f5_replay_does_not_leak_key`, `test_t2_f5_replay_conflicting_payload`, `test_t2_f5_global_response_text_regex_clean`, `test_t2_f5_concurrent_replay_race`, `test_t2_f5_error_state_info_disclosure` | `test_t3_cross_webhook_replay_continuity` | `test_t4_adversary_attack_gauntlet` |
| **F6** | Free Key Claim Hardening | `test_t1_f6_claim_initiation_without_key_leak`, `test_t1_f6_authenticated_web_claim_access`, `test_t1_f6_f5_refresh_consistency`, `test_t1_f6_daily_ip_quota_enforcement`, `test_t1_f6_natural_token_expiration` | `test_t2_f6_claim_post_omits_key_assertion`, `test_t2_f6_ip_spoofing_forwarded_for_blocked`, `test_t2_f6_tampered_claim_token_403`, `test_t2_f6_malformed_token_format_403`, `test_t2_f6_duplicate_claim_rate_limiting` | `test_t3_cross_free_claim_to_rollback` | `test_t4_free_trial_user_journey` |
| **F7** | CF Worker Backdoor Removal | `test_t1_f7_admin_login_configured_password`, `test_t1_f7_admin_auth_bearer_token`, `test_t1_f7_admin_auth_cookie`, `test_t1_f7_admin_generate_key_authorized`, `test_t1_f7_admin_revoke_key_authorized` | `test_t2_f7_rejects_backdoor_admin_chess_pro_2026`, `test_t2_f7_bearer_rejects_backdoor`, `test_t2_f7_fails_closed_when_env_unset`, `test_t2_f7_rejects_empty_whitespace_passwords`, `test_t2_f7_constant_time_comparison` | `test_t3_cross_admin_revocation_propagates` | `test_t4_adversary_attack_gauntlet` |
| **F8** | CF Worker Endpoint & CORS | `test_t1_f8_public_health_accessible`, `test_t1_f8_public_check_key_accessible`, `test_t1_f8_admin_dashboard_slug_accessible`, `test_t1_f8_api_security_headers_present`, `test_t1_f8_html_security_headers_present` | `test_t2_f8_admin_path_does_not_redirect_slug`, `test_t2_f8_admin_rejects_cross_origin_options`, `test_t2_f8_admin_rejects_cross_origin_post`, `test_t2_f8_admin_html_cannot_be_framed`, `test_t2_f8_wrangler_toml_secret_purged` | `test_t3_cross_cors_isolation_admin_vs_public` | `test_t4_adversary_attack_gauntlet` |
| **F9** | Supabase Row Level Security | `test_t1_f9_migration_enables_rls_all_tables`, `test_t1_f9_service_role_full_access`, `test_t1_f9_idempotent_policy_ddl`, `test_t1_f9_embedded_schema_includes_rls`, `test_t1_f9_service_role_insert_and_query` | `test_t2_f9_anon_role_cannot_select_licenses`, `test_t2_f9_anon_role_cannot_insert_licenses`, `test_t2_f9_anon_role_cannot_read_payments`, `test_t2_f9_anon_role_cannot_read_activation_logs`, `test_t2_f9_authenticated_cannot_bypass_rls` | `test_t3_cross_webhook_service_role_rls` | `test_t4_adversary_attack_gauntlet` |
| **F10** | Client Anti-Debug / Hook Watchdog | `test_t1_f10_watchdog_clean_environment`, `test_t1_f10_kernel32_bindings_exist`, `test_t1_f10_heartbeat_updates_periodically`, `test_t1_f10_api_prologue_clean`, `test_t1_f10_watchdog_thread_is_daemon` | `test_t2_f10_detects_is_debugger_present`, `test_t2_f10_detects_check_remote_debugger`, `test_t2_f10_detects_jmp_hook_in_critical_api`, `test_t2_f10_detects_int3_breakpoint`, `test_t2_f10_compromise_poisons_arrow_scale` | `test_t3_cross_watchdog_cascade_overlay_ipc` | `test_t4_debugger_attach_simulation` |
| **F11** | Overlay IPC Authentication | `test_t1_f11_overlay_server_binds_8765`, `test_t1_f11_generates_high_entropy_token`, `test_t1_f11_post_update_valid_bearer`, `test_t1_f11_get_cal_valid_bearer`, `test_t1_f11_userscript_accessible` | `test_t2_f11_missing_auth_header_rejected_401`, `test_t2_f11_invalid_bearer_token_rejected_401`, `test_t2_f11_malformed_auth_header_rejected`, `test_t2_f11_cors_rejects_external_origin`, `test_t2_f11_constant_time_token_check` | `test_t3_cross_overlay_ipc_rendering_pipeline` | `test_t4_malicious_browser_tab_xss_probe` |
| **F12** | Cryptographic Coordinate Gating | `test_t1_f12_derive_arrow_scale_factor_valid`, `test_t1_f12_coordinate_scaling_dimensions`, `test_t1_f12_cryptographic_derivation_deterministic`, `test_t1_f12_lifetime_license_derives_scale`, `test_t1_f12_coordinate_gating_scales_dpi` | `test_t2_f12_tampered_signature_zeroes_scale`, `test_t2_f12_expired_session_zeroes_scale`, `test_t2_f12_null_session_returns_zero`, `test_t2_f12_boolean_bypass_fails_coordinate_math`, `test_t2_f12_hwid_mismatch_zeroes_scale` | `test_t3_cross_crypto_gating_to_paint_event` | `test_t4_binary_patch_simulation` |
| **F13** | PyInstaller Hardening & Exclusion | `test_t1_f13_spec_valid_python_syntax`, `test_t1_f13_spec_optimize_level_2`, `test_t1_f13_spec_excludes_sensitive_modules`, `test_t1_f13_build_exe_references_hardened_spec`, `test_t1_f13_main_py_no_sensitive_imports` | `test_t2_f13_client_cannot_import_keygen`, `test_t2_f13_client_cannot_import_webhooks`, `test_t2_f13_optimize_2_removes_docstrings`, `test_t2_f13_optimize_2_strips_asserts`, `test_t2_f13_spec_datas_no_sensitive_files` | `test_t3_cross_hardened_spec_build_boots` | `test_t4_pyinstaller_carchive_extraction_audit` |
| **F14** | Regression Testing & Verification | `test_t1_f14_existing_activation_window_intact`, `test_t1_f14_existing_crypto_web_keys_intact`, `test_t1_f14_existing_engine_dropdown_intact`, `test_t1_f14_existing_no_autolaunch_intact`, `test_t1_f14_existing_palette_ui_intact` | `test_t2_f14_multi_device_hwid_reset_limit`, `test_t2_f14_status_card_state_transitions`, `test_t2_f14_color_picker_boundary_values`, `test_t2_f14_engine_card_rapid_toggle_debounce`, `test_t2_f14_splash_progress_step_integrity` | `test_t3_cross_device_migration_rebinding` | `test_t4_commercial_customer_lifecycle` |
| **F15** | Comprehensive Audit Verification | `test_t1_f15_audit_report_file_exists`, `test_t1_f15_audit_report_covers_all_4_domains`, `test_t1_f15_audit_report_has_cve_severity_table`, `test_t1_f15_audit_report_cites_source_lines`, `test_t1_f15_audit_report_documents_patches` | `test_t2_f15_zero_hardcoded_secrets_across_repo`, `test_t2_f15_zero_private_seeds_in_client_dir`, `test_t2_f15_zero_wildcard_cors_on_admin_api`, `test_t2_f15_zero_unprotected_tables_in_schema`, `test_t2_f15_all_critical_vulnerabilities_remediated` | `test_t3_cross_security_audit_remediation_integrity` | `test_t4_adversary_attack_gauntlet` |

---

## 6. Acceptance Criteria & Gate Signal (`TEST_READY.md`)

The test suite is officially accepted when:
1. 100% of existing unit and component tests (37+ tests) pass without errors.
2. 100% of the newly implemented 4-tier E2E and security tests in `tests/test_e2e_security.py` pass without errors.
3. No dummy or facade tests exist.
4. Gate readiness artifact `TEST_READY.md` is emitted documenting final test metrics, environment details, and execution logs.
