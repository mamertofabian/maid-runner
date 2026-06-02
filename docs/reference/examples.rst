Usage Examples
==============

Validate One Manifest
---------------------

:func:`maid_runner.validate` validates a single manifest file and returns a
:class:`maid_runner.ValidationResult`.

.. code-block:: python

   from maid_runner import ValidationResult, validate

   result: ValidationResult = validate("manifests/add-auth.manifest.yaml")
   if not result.success:
       for error in result.errors:
           print(f"{error.code}: {error.message}")

Validate A Manifest Directory
-----------------------------

:func:`maid_runner.validate_all` validates every active manifest in a directory
and returns a :class:`maid_runner.BatchValidationResult`.

.. code-block:: python

   from maid_runner import BatchValidationResult, validate_all

   batch: BatchValidationResult = validate_all("manifests/")
   print(f"{batch.passed}/{batch.total_manifests} manifests passed")

Load, Edit, And Save A Manifest
-------------------------------

:func:`maid_runner.load_manifest` and :func:`maid_runner.save_manifest` expose
the manifest parser and writer used by the CLI.

.. code-block:: python

   from maid_runner import Manifest, load_manifest, save_manifest

   manifest: Manifest = load_manifest("manifests/add-auth.manifest.yaml")
   manifest.metadata["reviewed_by"] = "api-reference-example"
   save_manifest(manifest, "manifests/add-auth.manifest.yaml")

Use The Validation Engine
-------------------------

:class:`maid_runner.ValidationEngine` is the lower-level entry point when an
application needs to reuse a configured engine across calls.

.. code-block:: python

   from maid_runner import ValidationEngine

   engine = ValidationEngine(project_root=".")
   result = engine.validate("manifests/add-auth.manifest.yaml")
   print(result.success)

Work With Manifest Chains
-------------------------

:class:`maid_runner.ManifestChain` gives callers direct access to manifest-chain
resolution when they need to inspect effective task history.

.. code-block:: python

   from maid_runner import ManifestChain

   chain = ManifestChain("manifests")
   active_manifests = chain.active_manifests()
   print([manifest.source_path for manifest in active_manifests])

Generate A Snapshot
-------------------

:func:`maid_runner.generate_snapshot` creates a manifest-style snapshot from an
existing source file.

.. code-block:: python

   from maid_runner import generate_snapshot

   snapshot = generate_snapshot("maid_runner/core/validate.py")
   print(snapshot.files_snapshot[0].path)

Register Validators
-------------------

:class:`maid_runner.ValidatorRegistry` stores the language validators used by
validation flows.

.. code-block:: python

   from maid_runner import ValidatorRegistry

   registry = ValidatorRegistry.with_builtin_validators()
   print(sorted(registry.supported_extensions()))
