# octopOS Architecture Diagrams

## 1. Four-Tier Hierarchy Overview

```mermaid
graph TB
    subgraph Layer0["Layer 0: Governance"]
        S[Supervisor Agent<br/>Security & Compliance]
    end
    
    subgraph Layer1["Layer 1: Strategy"]
        MB[Main Brain<br/>Intent Analysis & Planning]
    end
    
    subgraph Layer2["Layer 2: Specialists"]
        CA[Coder Agent]
        SH[Self-Healing Agent]
        MA[Manager Agent]
    end
    
    subgraph Layer3["Layer 3: Execution"]
        W1[Worker - Docker]
        W2[Worker - Docker]
        W3[Worker - Docker]
        P1[Primitive: FileOps]
        P2[Primitive: S3Ops]
        P3[Primitive: GitOps]
    end
    
    S -.->|Monitor & Audit| MB
    S -.->|Approve/Reject| CA
    MB -->|Delegate| CA
    MB -->|Coordinate| MA
    CA -->|Write/Test| P3
    SH -->|Fix| W1
    MA -->|Manage| W1
    MA -->|Manage| W2
    MA -->|Manage| W3
    W1 -->|Execute| P1
    W2 -->|Execute| P2
    W3 -->|Execute| P3
```

## 2. Message Flow Architecture

```mermaid
sequenceDiagram
    participant User
    participant CLI as CLI Interface
    participant MB as Main Brain
    participant MA as Manager Agent
    participant CA as Coder Agent
    participant S as Supervisor
    participant Worker as Docker Worker
    
    User->>CLI: Create a new API endpoint
    CLI->>MB: OctoMessage: TASK
    
    MB->>MB: Intent Classification
    MB->>MB: Task Decomposition
    
    MB->>MA: OctoMessage: TASK_LIST
    MA->>CA: OctoMessage: TASK (create primitive)
    
    CA->>CA: Generate code
    CA->>S: OctoMessage: APPROVAL_REQUEST
    
    S->>S: Security scan
    S->>CA: OctoMessage: APPROVAL_GRANTED
    
    CA->>MA: OctoMessage: STATUS_UPDATE
    MA->>Worker: OctoMessage: TASK (execute)
    
    Worker->>Worker: Run in sandbox
    Worker->>MA: OctoMessage: STATUS_UPDATE (complete)
    
    MA->>MB: OctoMessage: STATUS_UPDATE
    MB->>CLI: Response
    CLI->>User: API endpoint created successfully
```

## 3. Dynamic Tool Creation Flow

```mermaid
flowchart TD
    A[User Request: New Capability Needed] --> B{Tool Exists?}
    B -->|Yes| C[Retrieve from LanceDB]
    B -->|No| D[Trigger Coder Agent]
    
    C --> E[Execute Existing Tool]
    
    D --> F[Generate Primitive Code]
    F --> G[Write Tests]
    G --> H[Self-Healing: Validate]
    
    H -->|Tests Pass| I[Request Supervisor Approval]
    H -->|Tests Fail| J[Auto-Fix Iteration]
    J --> H
    
    I --> K{Approved?}
    K -->|Yes| L[Add to LanceDB]
    K -->|No| M[Return Error to User]
    
    L --> N[Index Documentation]
    N --> O[Available for Future Use]
    
    E --> P[Return Result]
    O --> P
    M --> Q[Suggest Alternative]
```

## 4. Memory Architecture

```mermaid
flowchart LR
    subgraph WorkingMemory["Working Memory"]
        WM1[Current Session Context]
        WM2[Active Tasks]
        WM3[Conversation History]
    end
    
    subgraph LanceDB["LanceDB Vector Store"]
        VM1[Primitive Docs<br/>Embeddings]
        VM2[User Facts<br/>Embeddings]
        VM3[Past Conversations<br/>Embeddings]
    end
    
    subgraph UserProfile["User Profile"]
        UP1[Persona Config]
        UP2[Preferences]
        UP3[AWS Settings]
    end
    
    MB[Main Brain] <-->|Query/Store| WM1
    MB <-->|Semantic Search| VM1
    MB <-->|Load/Save| UP1
    
    CA[Coder Agent] <-->|Read| VM1
    CA -->|Write| VM1
    
    FE[Fact Extractor] -->|Extract| WM3
    FE -->|Store| VM2
```

## 5. Omni-Channel Interface Architecture

```mermaid
flowchart TB
    subgraph InputChannels["Input Channels"]
        CLI[CLI/Terminal]
        TG[Telegram]
        SL[Slack]
        WA[WhatsApp]
    end
    
    subgraph MessageAdapter["Message Adapter"]
        MA[MessageAdapter]
        MF[Format Normalizer]
        FH[File Handler]
    end
    
    subgraph CoreEngine["Core Engine"]
        OM[OctoMessage Queue]
        MB[Main Brain]
    end
    
    subgraph OutputChannels["Output Channels"]
        RCLI[CLI Response]
        RTG[Telegram Bot]
        RSL[Slack Bot]
        RWA[WhatsApp Bot]
    end
    
    CLI -->|Text/File| MA
    TG -->|API Webhook| MA
    SL -->|Event API| MA
    WA -->|Business API| MA
    
    MA --> MF
    MF -->|File uploads| FH
    FH -->|Vectorize| OM
    MF -->|Standardize| OM
    
    OM --> MB
    MB --> OM
    
    OM --> RCLI
    OM --> RTG
    OM --> RSL
    OM --> RWA
```

## 6. Task Scheduling Architecture

```mermaid
flowchart TB
    subgraph TaskSources["Task Sources"]
        U1[One-off User Request]
        U2[Recurring Schedule]
        U3[System Event]
    end
    
    subgraph OctoQueue["OctoQueue"]
        TD[(Task Database<br/>SQLite/LanceDB)]
        SM[State Machine]
        PM[Priority Manager]
    end
    
    subgraph Scheduler["Scheduler"]
        SCH[Scheduler Engine]
        CRON[Cron Parser]
        EB[AWS EventBridge<br/>Cloud only]
    end
    
    subgraph Execution["Execution"]
        W[Worker Pool]
        T[Task Executor]
    end
    
    U1 -->|Immediate| TD
    U2 -->|Schedule| SCH
    U3 -->|Trigger| SCH
    
    SCH -->|Parse| CRON
    CRON -->|Store| TD
    EB -->|Cloud Trigger| TD
    
    TD <-->|Update| SM
    SM -->|Prioritize| PM
    PM -->|Dispatch| W
    
    W -->|Run| T
    T -->|Update State| TD
```

## 7. Security & Isolation Model

```mermaid
flowchart TB
    subgraph HostSystem["Host System"]
        HOST[User's Machine/AWS]
        
        subgraph OctoOSCore["octopOS Core"]
            ORCH[Orchestrator]
            AGENTS[Specialist Agents]
        end
        
        subgraph DockerSandbox["Docker Sandbox"]
            DOCKER[Docker Daemon]
            
            subgraph EphemeralContainers["Ephemeral Containers"]
                C1[Worker 1<br/>Task A]
                C2[Worker 2<br/>Task B]
                C3[Worker 3<br/>Task C]
            end
        end
    end
    
    subgraph ExternalServices["External Services"]
        AWS[AWS Bedrock]
        CW[CloudWatch]
        GR[Guardrails]
    end
    
    ORCH -->|Spawn| DOCKER
    AGENTS -->|Delegate| C1
    AGENTS -->|Delegate| C2
    AGENTS -->|Delegate| C3
    
    C1 -->|Read-only mount| HOST
    C2 -->|Read-only mount| HOST
    C3 -->|Read-only mount| HOST
    
    ORCH <-->|HTTPS| AWS
    ORCH -->|Logs| CW
    AWS -->|Filter| GR
    
    C1 -.->|No direct access| AWS
    C2 -.->|No direct access| AWS
    C3 -.->|No direct access| AWS
```
