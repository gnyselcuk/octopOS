# octopOS Testing Strategy Plan
## Unit Tests & Real-World Test Scenarios

---

## 1. Overview

Bu doküman octopOS projesi için kapsamlı test stratejisi, unit test planı ve gerçek dünya test senaryolarını içerir.

### Test Piramidi

```
         /\
        /  \     E2E Tests (Browser automation, full flows)
       /----\
      /      \   Integration Tests (API, DB, External services)
     /--------\
    /          \ Unit Tests (Functions, classes, modules)
   /------------\
```

---

## 2. Unit Test Planı

### 2.1 Test Edilecek Modüller (Öncelik Sırasına Göre)

| Priority | Module | Reason |
|----------|--------|--------|
| P0 | `engine/message.py` | Core communication protocol |
| P0 | `engine/supervisor.py` | Security & approval system |
| P0 | `primitives/base_primitive.py` | All tools base class |
| P0 | `workers/base_worker.py` | Task execution foundation |
| P1 | `engine/memory/` | Memory management |
| P1 | `engine/scheduler.py` | Task scheduling |
| P1 | `workers/ephemeral_container.py` | Docker isolation |
| P1 | `workers/worker_pool.py` | Worker management |
| P2 | `interfaces/message_adapter.py` | Platform abstraction |
| P2 | `specialist/coder_agent.py` | Code generation |
| P2 | `specialist/self_healing_agent.py` | Error recovery |
| P2 | `primitives/*` | Tool implementations |
| P3 | `interfaces/telegram/` | Telegram bot |
| P3 | `interfaces/slack/` | Slack bot |
| P3 | `interfaces/cli/` | CLI interface |

### 2.2 Test Yapısı

```
tests/
├── __init__.py
├── conftest.py                    # Global fixtures
├── unit/                          # Unit tests
│   ├── __init__.py
│   ├── engine/
│   │   ├── test_message.py
│   │   ├── test_supervisor.py
│   │   ├── test_scheduler.py
│   │   └── memory/
│   │       ├── test_semantic_memory.py
│   │       ├── test_intent_finder.py
│   │       └── test_working_memory.py
│   ├── workers/
│   │   ├── test_base_worker.py
│   │   ├── test_ephemeral_container.py
│   │   └── test_worker_pool.py
│   ├── primitives/
│   │   ├── test_base_primitive.py
│   │   ├── test_file_operations.py
│   │   └── test_bash_executor.py
│   ├── specialist/
│   │   ├── test_coder_agent.py
│   │   └── test_self_healing_agent.py
│   └── interfaces/
│       ├── test_message_adapter.py
│       └── telegram/
│           └── test_telegram_bot.py
├── integration/                   # Integration tests
│   ├── __init__.py
│   ├── test_worker_container.py
│   ├── test_memory_database.py
│   ├── test_agent_collaboration.py
│   └── test_api_endpoints.py
├── e2e/                          # End-to-end tests
│   ├── __init__.py
│   ├── test_task_execution.py
│   ├── test_multi_agent_workflow.py
│   └── test_error_recovery.py
└── fixtures/                     # Test fixtures & mocks
    ├── __init__.py
    ├── mock_aws.py
    ├── mock_docker.py
    ├── mock_bedrock.py
    └── sample_data.py
```

### 2.3 Unit Test Senaryoları

#### 2.3.1 Message Protocol Tests (`engine/message.py`)

```python
class TestOctoMessage:
    """Test OctoMessage creation and validation."""
    
    # Test Cases
    - test_create_valid_task_message
    - test_create_error_message_with_payload
    - test_message_validation_missing_required_fields
    - test_message_serialization_deserialization
    - test_message_with_agent_context
    - test_approval_request_flow
    - test_status_update_progression
    - test_message_priority_handling
    - test_message_threading_conversation_id
    - test_invalid_message_type_rejection
```

#### 2.3.2 Supervisor Tests (`engine/supervisor.py`)

```python
class TestSupervisor:
    """Test security and approval system."""
    
    # Security Tests
    - test_guardrails_content_filtering
    - test_anomaly_detection_threshold
    - test_approval_required_for_coder_agent
    - test_approval_required_for_file_deletion
    - test_rejection_of_harmful_code
    - test_privilege_escalation_detection
    
    # Approval Flow Tests
    - test_approve_new_primitive
    - test_deny_unsafe_primitive
    - test_approval_timeout_handling
    - test_batch_approval_workflow
    - test_revoke_previous_approval
    
    # Monitoring Tests
    - test_cloudwatch_log_forwarding
    - test_anomaly_alert_generation
    - test_audit_trail_logging
```

#### 2.3.3 Base Worker Tests (`workers/base_worker.py`)

```python
class TestBaseWorker:
    """Test worker lifecycle and execution."""
    
    # Lifecycle Tests
    - test_worker_initialization
    - test_worker_start_transition
    - test_worker_destroy_cleanup
    - test_worker_state_machine_transitions
    - test_worker_error_state_recovery
    
    # Execution Tests
    - test_execute_simple_command
    - test_execute_with_timeout
    - test_execute_with_resource_limits
    - test_execute_handles_errors
    - test_concurrent_task_rejection
    - test_task_result_formatting
    
    # Configuration Tests
    - test_worker_config_validation
    - test_resource_limit_enforcement
    - test_security_settings_application
```

#### 2.3.4 Ephemeral Container Tests (`workers/ephemeral_container.py`)

```python
class TestEphemeralContainer:
    """Test Docker container management."""
    
    # Container Lifecycle
    - test_container_creation_with_config
    - test_container_start_execution
    - test_container_destroy_cleanup
    - test_container_id_persistence
    
    # Execution Tests
    - test_execute_command_success
    - test_execute_command_failure
    - test_execute_timeout_handling
    - test_execute_with_environment_vars
    - test_execute_with_volume_mounts
    
    # Security Tests
    - test_security_options_applied
    - test_read_only_filesystem
    - test_network_mode_none
    - test_capability_dropping
    - test_user_namespace_isolation
    
    # Resource Tests
    - test_memory_limit_enforcement
    - test_cpu_limit_enforcement
    - test_disk_quota_enforcement
    - test_pid_limit_enforcement
```

#### 2.3.5 Worker Pool Tests (`workers/worker_pool.py`)

```python
class TestWorkerPool:
    """Test worker pool management."""
    
    # Pool Management
    - test_pool_initialization_with_min_workers
    - test_pool_shutdown_cleanup
    - test_acquire_release_worker_cycle
    
    # Scaling Tests
    - test_scale_up_on_high_load
    - test_scale_down_on_low_load
    - test_scale_cooldown_respect
    - test_max_workers_limit
    - test_min_workers_maintenance
    
    # Task Distribution
    - test_task_queue_management
    - test_task_timeout_handling
    - test_task_retry_on_failure
    - test_priority_queue_handling
    
    # Health Tests
    - test_health_check_interval
    - test_worker_failure_detection
    - test_unhealthy_worker_replacement
```

#### 2.3.6 Base Primitive Tests (`primitives/base_primitive.py`)

```python
class TestBasePrimitive:
    """Test primitive base class."""
    
    # Interface Tests
    - test_abstract_methods_require_implementation
    - test_name_property_requirement
    - test_description_property_requirement
    - test_execute_method_requirement
    
    # Parameter Tests
    - test_parameter_validation_success
    - test_parameter_validation_missing_required
    - test_parameter_validation_wrong_type
    - test_parameter_default_values
    
    # Result Tests
    - test_primitive_result_creation
    - test_result_serialization
    - test_error_result_handling
```

#### 2.3.7 Semantic Memory Tests (`engine/memory/semantic_memory.py`)

```python
class TestSemanticMemory:
    """Test vector memory operations."""
    
    # Storage Tests
    - test_store_text_embedding
    - test_store_with_metadata
    - test_store_batch_documents
    - test_update_existing_entry
    
    # Retrieval Tests
    - test_semantic_search_similarity
    - test_search_with_filters
    - test_search_limit_enforcement
    - test_search_threshold_filtering
    
    # LanceDB Integration
    - test_table_creation
    - test_schema_validation
    - test_embedding_generation
    - test_persistence_across_restarts
```

#### 2.3.8 Intent Finder Tests (`engine/memory/intent_finder.py`)

```python
class TestIntentFinder:
    """Test intent classification."""
    
    # Classification Tests
    - test_classify_chat_intent
    - test_classify_operational_intent
    - test_classify_ambiguous_intent
    - test_confidence_score_calculation
    
    # Primitive Selection
    - test_find_relevant_primitives
    - test_rank_primitive_candidates
    - test_limit_top_k_results
    - test_fallback_on_no_match
    
    # Integration Tests
    - test_semantic_search_integration
    - test_llm_decision_integration
```

#### 2.3.9 Scheduler Tests (`engine/scheduler.py`)

```python
class TestScheduler:
    """Test task scheduling."""
    
    # Scheduling Tests
    - test_schedule_immediate_task
    - test_schedule_delayed_task
    - test_schedule_recurring_task
    - test_cron_expression_parsing
    
    # Execution Tests
    - test_task_execution_callback
    - test_task_failure_retry
    - test_max_retry_limit
    - test_retry_backoff_calculation
    
    # Management Tests
    - test_cancel_scheduled_task
    - test_pause_resume_scheduler
    - test_get_scheduled_tasks_list
    - test_task_priority_handling
```

#### 2.3.10 Coder Agent Tests (`specialist/coder_agent.py`)

```python
class TestCoderAgent:
    """Test code generation agent."""
    
    # Code Generation
    - test_generate_primitive_tool
    - test_generate_with_requirements
    - test_generate_error_handling_code
    - test_generate_documentation
    
    # Validation
    - test_syntax_validation_success
    - test_syntax_validation_failure
    - test_security_scan_pass
    - test_security_scan_violation
    
    # Integration
    - test_bedrock_api_integration
    - test_self_healing_agent_callback
```

#### 2.3.11 Self-Healing Agent Tests (`specialist/self_healing_agent.py`)

```python
class TestSelfHealingAgent:
    """Test error recovery agent."""
    
    # Error Analysis
    - test_parse_python_error
    - test_parse_docker_error
    - test_classify_error_type
    - test_suggest_fix_strategy
    
    # Fix Application
    - test_apply_code_fix
    - test_apply_config_fix
    - test_apply_retry_strategy
    - test_escalate_on_failure
    
    # Recovery Flow
    - test_full_recovery_workflow
    - test_recovery_success_verification
```

#### 2.3.12 Message Adapter Tests (`interfaces/message_adapter.py`)

```python
class TestMessageAdapter:
    """Test platform message normalization."""
    
    # Normalization Tests
    - test_normalize_telegram_message
    - test_normalize_slack_message
    - test_normalize_whatsapp_message
    - test_normalize_cli_input
    
    # Attachment Tests
    - test_handle_text_attachment
    - test_handle_file_attachment
    - test_handle_image_attachment
    - test_handle_voice_attachment
    
    # Context Tests
    - test_extract_user_context
    - test_extract_conversation_context
    - test_extract_reply_context
```

---

## 3. Test Fixtures ve Mock Stratejisi

### 3.1 Global Fixtures (`conftest.py`)

```python
# Fixtures

@pytest.fixture
def mock_bedrock_client():
    """Mock AWS Bedrock client."""
    
@pytest.fixture
def mock_docker_client():
    """Mock Docker client."""
    
@pytest.fixture
def mock_lancedb():
    """Mock LanceDB connection."""
    
@pytest.fixture
def temp_workspace(tmp_path):
    """Temporary workspace directory."""
    
@pytest.fixture
def sample_octo_message():
    """Sample OctoMessage instance."""
    
@pytest.fixture
def sample_agent_context():
    """Sample AgentContext instance."""
    
@pytest.fixture
def event_loop():
    """Event loop for async tests."""
```

### 3.2 Mock Implementations

```python
# Mock AWS Services
class MockBedrockRuntime:
    """Mock Bedrock runtime client."""
    
class MockCloudWatch:
    """Mock CloudWatch client."""
    
class MockDynamoDB:
    """Mock DynamoDB table."""
    
class MockS3:
    """Mock S3 bucket."""

# Mock Docker
class MockDockerContainer:
    """Mock Docker container."""
    
class MockDockerClient:
    """Mock Docker client."""

# Mock External APIs
class MockTelegramAPI:
    """Mock Telegram Bot API."""
    
class MockSlackAPI:
    """Mock Slack API."""
```

---

## 4. Gerçek Dünya Test Senaryoları

### 4.1 End-to-End Senaryolar

#### Senaryo 1: Basit Görev Yürütme
```gherkin
Feature: Basit Görev Yürütme
  
  Scenario: Kullanıcı bir Python betiği çalıştırmak istiyor
    Given kullanıcı CLI arayüzünde
    When "Python ile 2+2 hesapla" mesajını gönderir
    Then sistem niyeti analiz eder
    And uygun primitive'i seçer
    And kodu sandbox içinde çalıştırır
    And sonucu kullanıcıya döndürür
    And container'ı temizler
```

#### Senaryo 2: Yeni Primitive Oluşturma
```gherkin
Feature: Dinamik Primitive Geliştirme
  
  Scenario: Mevcut olmayan bir araç için geliştirme
    Given kullanıcı "GitHub'dan repo klonla" isteği gönderir
    When sistem uygun primitive bulamaz
    Then Coder Agent devreye girer
    And yeni primitive kodunu yazar
    And Self-Healing Agent test eder
    And Supervisor onaylar
    And primitive'i kayıt defterine ekler
    And kullanıcıya sonucu döndürür
```

#### Senaryo 3: Multi-Agent İş Akışı
```gherkin
Feature: Karmaşık İş Akışı
  
  Scenario: Web scraping ve analiz görevi
    Given kullanıcı "Haber sitelerinden AI haberlerini topla ve özetle" isteği gönderir
    When Main Brain görevi alt görevlere böler
    Then Browser Agent web sitelerini ziyaret eder
    And Coder Agent scraping kodunu yazar
    And Worker Agent kodu çalıştırır
    And Manager Agent sonuçları birleştirir
    And kullanıcıya özet rapor sunar
```

#### Senaryo 4: Hata Kurtarma
```gherkin
Feature: Self-Healing Sistemi
  
  Scenario: Çalışma zamanı hatası durumunda kurtarma
    Given Worker Agent bir kod çalıştırırken hata alır
    When Self-Healing Agent hatayı analiz eder
    Then hata tipini sınıflandırır
    And düzeltme stratejisi önerir
    And kodu düzeltir veya yapılandırmayı ayarlar
    And yeniden deneme yapar
    And başarı durumunu raporlar
```

#### Senaryo 5: Çoklu Platform Entegrasyonu
```gherkin
Feature: Omni-Channel Communication
  
  Scenario: Aynı görev farklı platformlardan
    Given kullanıcı Telegram'dan "S3 bucket listesi al" gönderir
    And başka kullanıcı Slack'ten aynı görevi gönderir
    When sistem her iki platformdan mesajı alır
    Then Message Adapter normalize eder
    And aynı iş mantığını uygular
    And her platforma uygun yanıt formatında döner
```

### 4.2 Entegrasyon Test Senaryoları

#### 4.2.1 Database Entegrasyonu

```python
class TestLanceDBIntegration:
    """Test LanceDB integration."""
    
    def test_memory_persistence(self):
        """Test that memory survives restarts."""
        
    def test_concurrent_access(self):
        """Test concurrent database access."""
        
    def test_embedding_consistency(self):
        """Test embedding generation consistency."""
```

#### 4.2.2 Docker Entegrasyonu

```python
class TestDockerIntegration:
    """Test Docker integration."""
    
    def test_container_isolation(self):
        """Test container filesystem isolation."""
        
    def test_network_isolation(self):
        """Test container network isolation."""
        
    def test_resource_limits(self):
        """Test resource limit enforcement."""
```

#### 4.2.3 AWS Entegrasyonu

```python
class TestAWSIntegration:
    """Test AWS service integration."""
    
    def test_bedrock_invocation(self):
        """Test Bedrock model invocation."""
        
    def test_guardrails_application(self):
        """Test Guardrails content filtering."""
        
    def test_cloudwatch_logging(self):
        """Test CloudWatch log shipping."""
```

### 4.3 Performans Test Senaryoları

#### 4.3.1 Yük Testleri

```python
class TestLoadPerformance:
    """Test system under load."""
    
    def test_concurrent_task_execution(self):
        """Test 100 concurrent tasks."""
        
    def test_memory_usage_under_load(self):
        """Test memory usage with many workers."""
        
    def test_response_time_percentiles(self):
        """Test p95, p99 response times."""
```

#### 4.3.2 Stres Testleri

```python
class TestStressScenarios:
    """Test system under stress."""
    
    def test_worker_pool_exhaustion(self):
        """Test behavior when all workers busy."""
        
    def test_queue_overflow_handling(self):
        """Test queue overflow behavior."""
        
    def test_recovery_from_overload(self):
        """Test recovery after overload."""
```

### 4.4 Güvenlik Test Senaryoları

#### 4.4.1 Sandbox Güvenliği

```python
class TestSandboxSecurity:
    """Test sandbox isolation."""
    
    def test_privilege_escalation_prevention(self):
        """Test that containers can't escalate privileges."""
        
    def test_filesystem_escape_prevention(self):
        """Test container escape prevention."""
        
    def test_network_access_blocking(self):
        """Test network isolation."""
        
    def test_resource_exhaustion_prevention(self):
        """Test resource limit enforcement."""
```

#### 4.4.2 Input Güvenliği

```python
class TestInputSecurity:
    """Test input validation."""
    
    def test_sql_injection_prevention(self):
        """Test SQL injection protection."""
        
    def test_command_injection_prevention(self):
        """Test command injection protection."""
        
    def test_path_traversal_prevention(self):
        """Test path traversal protection."""
        
    def test_malicious_code_detection(self):
        """Test detection of malicious code."""
```

#### 4.4.3 Supervisor Güvenliği

```python
class TestSupervisorSecurity:
    """Test supervisor security features."""
    
    def test_harmful_content_blocking(self):
        """Test blocking of harmful content."""
        
    def test_sensitive_data_masking(self):
        """Test sensitive data protection."""
        
    def test_audit_trail_completeness(self):
        """Test audit trail logging."""
```

---

## 5. Test Altyapısı ve CI/CD

### 5.1 Pytest Yapılandırması

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --cov=src
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=80
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow tests
    security: Security tests
    performance: Performance tests
```

### 5.2 Test Kategorileri

```bash
# Run only unit tests
pytest -m unit

# Run integration tests
pytest -m integration

# Run all tests except slow ones
pytest -m "not slow"

# Run security tests
pytest -m security

# Run with coverage
pytest --cov=src --cov-report=html
```

### 5.3 CI/CD Pipeline

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest -m unit --cov=src --cov-report=xml
      
  integration-tests:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
    steps:
      - uses: actions/checkout@v3
      - run: pip install -e ".[dev]"
      - run: pytest -m integration
      
  security-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -e ".[dev]"
      - run: pytest -m security
      - run: bandit -r src
      - run: safety check
```

### 5.4 Coverage Hedefleri

| Module | Target | Critical |
|--------|--------|----------|
| engine/message.py | 95% | Yes |
| engine/supervisor.py | 90% | Yes |
| workers/* | 85% | Yes |
| primitives/base* | 90% | Yes |
| specialist/* | 80% | No |
| interfaces/* | 75% | No |
| utils/* | 70% | No |

---

## 6. Uygulama Yol Haritası

### Faz 1: Temel Test Altyapısı (Hafta 1)
- [ ] Test dizin yapısını oluştur
- [ ] conftest.py ve global fixtures
- [ ] Mock implementasyonları
- [ ] pytest.ini yapılandırması

### Faz 2: Kritik Modül Testleri (Hafta 2-3)
- [ ] engine/message.py tests
- [ ] engine/supervisor.py tests
- [ ] workers/base_worker.py tests
- [ ] primitives/base_primitive.py tests

### Faz 3: Workers ve Containers (Hafta 4)
- [ ] workers/ephemeral_container.py tests
- [ ] workers/worker_pool.py tests
- [ ] Docker integration tests

### Faz 4: Memory ve Scheduler (Hafta 5)
- [ ] engine/memory/* tests
- [ ] engine/scheduler.py tests
- [ ] LanceDB integration tests

### Faz 5: Specialist Agents (Hafta 6)
- [ ] specialist/coder_agent.py tests
- [ ] specialist/self_healing_agent.py tests
- [ ] specialist/manager_agent.py tests

### Faz 6: Interfaces (Hafta 7)
- [ ] interfaces/message_adapter.py tests
- [ ] interfaces/telegram/* tests
- [ ] interfaces/cli/* tests

### Faz 7: E2E ve Integration (Hafta 8)
- [ ] End-to-end test suite
- [ ] Integration test suite
- [ ] Performance benchmarks
- [ ] Security test suite

### Faz 8: CI/CD ve Otomasyon (Hafta 9)
- [ ] GitHub Actions workflow
- [ ] Coverage reporting
- [ ] Test automation

---

## 7. Ek Araçlar ve Öneriler

### 7.1 Test Veri Yönetimi

```python
# tests/fixtures/sample_data.py

SAMPLE_OCTO_MESSAGE = {
    "message_id": "test-msg-001",
    "type": "task",
    "payload": {
        "task": "calculate",
        "params": {"expression": "2 + 2"}
    },
    "agent_context": {
        "workspace_path": "/tmp/test",
        "aws_region": "us-east-1"
    }
}

SAMPLE_CONTAINER_CONFIG = {
    "image": "octopos-sandbox:latest",
    "memory_limit": "256m",
    "network_mode": "none"
}
```

### 7.2 Test Veritabanı Yönetimi

```python
@pytest.fixture(scope="function")
def test_memory_db(tmp_path):
    """Create isolated test database."""
    db_path = tmp_path / "test_memory.lance"
    # Initialize test database
    yield db_path
    # Cleanup
```

### 7.3 Docker Test Helpers

```python
@pytest.fixture(scope="module")
def docker_client():
    """Provide Docker client for tests."""
    import docker
    client = docker.from_env()
    yield client
    # Cleanup containers
```

---

## 8. Özet

Bu test planı octopOS projesi için:

1. **Kapsamlı Unit Test Coverage**: Tüm kritik modüller için detaylı test senaryoları
2. **Gerçek Dünya Senaryoları**: E2E, entegrasyon, performans ve güvenlik testleri
3. **Test Altyapısı**: Fixtures, mocks, ve CI/CD entegrasyonu
4. **Uygulama Yol Haritası**: 9 haftalık aşamalı uygulama planı

Test stratejisi projenin güvenilirliğini, güvenliğini ve bakılabilirliğini sağlamak için tasarlanmıştır.
