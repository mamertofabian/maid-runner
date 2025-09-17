### **MAID: The Manifest-driven AI Development Methodology (Updated)**

**Version:** 1.1
**Date:** September 18, 2025

#### **Abstract**

The Manifest-driven AI Development (MAID) methodology is a structured approach to software engineering that leverages AI agents for code implementation while ensuring architectural integrity, quality, and maintainability. It addresses the core challenge of AI code generation—its tendency to produce plausible but flawed code without architectural awareness—by shifting the developer's role from a direct implementer to a high-level architect who provides AI agents with perfectly isolated, testable, and explicit tasks. This is achieved through a workflow centered on a Task Manifest, a declarative file that defines a self-contained unit of work as part of a verifiable sequence. By combining this manifest with architectural patterns that promote extreme decoupling, MAID creates a predictable and scalable environment for AI-assisted development.

-----

#### **Core Principles**

The MAID methodology is founded on five core principles:

  * **Explicitness over Implicitness:** An AI agent's context must be explicitly defined. The agent should never have to guess which files to edit, what dependencies exist, or how to validate its work.
  * **Extreme Isolation:** A task given to an AI agent should be as isolated as possible from the wider codebase *at the time of its creation*. The goal is to create a temporary "micro-environment" for every task, minimizing the cognitive load on the LLM.
  * **Test-Driven Validation:** The sole measure of an AI's success is its ability to make a predefined set of tests pass. Tests are the contract and the "definition of done."
  * **Directed Dependency:** The software architecture must enforce a one-way flow of dependencies from volatile details (frameworks, databases) inward to stable business logic, as defined by Clean Architecture. This protects the core logic and simplifies tasks for the AI.
  * **Verifiable Chronology:** The current state of any module must be the verifiable result of applying its entire sequence of historical manifests. This ensures that the codebase has a transparent and reproducible history, preventing undocumented changes or "code drift."

-----

#### **The MAID Workflow**

The development process is broken down into five distinct phases, creating a clear and repeatable loop.

1.  **Phase 1: Goal Definition (Human Architect)**
    The human developer defines a high-level feature or bug fix. For example: "The system needs an endpoint to retrieve a user's profile by their ID."

2.  **Phase 2: Contract Generation (Architect Agent)**
    The human architect instructs an "Architect Agent" to create the contract for the work. The agent generates a comprehensive test suite defining the required behavior.

3.  **Phase 3: Human Review & Manifest Creation**
    The human architect reviews and validates the generated tests. This is the most critical quality gate. Once satisfied, the architect creates a `task-XXX.manifest.json` file, using a sequential identifier (e.g., `task-001`, `task-002`) to establish its place in the project's history.

4.  **Phase 4: Implementation (Developer Agent)**
    An automated system invokes a "Developer Agent" and provides it with the manifest file. The agent's workflow is as follows:

      * Read the manifest to load only the specified `editableFiles` and `readonlyFiles` into its context.
      * Write or modify the code based on the `goal` and its understanding of the tests.
      * The controlling script executes the `validationCommand` and the **Merging Validator**.
      * If tests or validation fail, the error output is automatically fed back into the agent's context for the next iteration. This loop continues until all conditions are met.

5.  **Phase 5: Integration**
    Once the task is complete, the newly implemented code and its corresponding manifest are committed. Because the work was performed against a strict, tested, and verifiable contract, it can be integrated with high confidence.

-----

#### **Core Components & Patterns**

  * **The Task Manifest**
    The Task Manifest is a JSON file that makes every task explicit and self-contained. It serves as an immutable record of a single change, forming one link in a chronological chain that defines the state of a module.

    ```json
    {
      "version": "1.1",
      "goal": "Implement the get_user_by_id function...",
      "editableFiles": ["src/repositories/user_repository.py"],
      "readonlyFiles": ["tests/test_user_repository.py"],
      "expectedArtifacts": { 
        "contains": [{"type": "function", "name": "get_user_by_id"}]
      },
      "validationCommand": "pytest tests/test_user_repository.py"
    }
    ```

  * **Prescribed Architectural Patterns**
    To enable the necessary isolation, projects following MAID must adhere to these patterns:

      * Hexagonal Architecture (Ports & Adapters)
      * Dependency Injection (DI)
      * Single Responsibility Principle (SRP)

-----

#### **Advanced Concepts & Future Techniques**

  * **The Migration Pattern & Merging Validator**
    Inspired by database migration systems, this pattern treats the codebase's state as the result of applying a sequence of manifest "migrations." A **Merging Validator** is used to enforce this. To validate a file, it performs these steps:

    1.  **Discover History:** It finds all manifests in chronological order that have ever modified the target file.
    2.  **Aggregate Artifacts:** It iterates through the sequence, merging the `expectedArtifacts` from each manifest into a final, comprehensive list. This allows for manifests that add, and potentially remove or rename, artifacts over time.
    3.  **Strict Validation:** It strictly compares the aggregated list against the public interface of the current file. The file's state must exactly match the state defined by its migration history, ensuring no un-manifested code exists.

  * **The "Scaffold and Fill" Pattern**
    A stricter version of the workflow where the Architect Agent not only creates tests but also creates the `editableFiles` with empty function signatures. This reduces the Developer Agent's task to pure implementation.

  * **The Guardian Agent and Self-Healing Codebases**
    For ongoing maintenance, a top-level "Guardian Agent" can run the entire test suite after any change is committed. If a change breaks tests, the Guardian can automatically generate a new manifest to dispatch a fix.

  * **Codebase as a Dependency Graph**
    By analyzing `import` statements, the entire codebase can be mapped as a Directed Acyclic Graph (DAG). This allows the system to automatically identify all necessary `readonlyFiles` for a given task and run tasks in parallel.
