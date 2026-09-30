"use strict";

const fs = require("fs");
const moduleApi = require("module");
const path = require("path");
const readline = require("readline");

const SOURCE_EXTENSIONS = [
  ".tsx",
  ".ts",
  ".jsx",
  ".js",
  ".mjs",
  ".cjs",
  ".mts",
  ".cts",
];

const IMPORT_RESOLUTION_PROJECT_CACHE = new Map();

function main() {
  const raw = fs.readFileSync(0, "utf8");
  const request = JSON.parse(raw);
  const projectRoot = path.resolve(String(request.projectRoot || "."));
  const ts = loadTypescript(projectRoot);

  if (request.command === "checkReturnContracts") {
    return checkReturnContracts(ts, projectRoot, request);
  }

  if (ts === null) {
    if (request.command === "resolveMany") {
      return Array.isArray(request.requests)
        ? request.requests.map(() => null)
        : [];
    }
    return null;
  }

  if (request.command === "resolveMany") {
    return resolveMany(ts, projectRoot, request);
  }
  const results = resolveMany(ts, projectRoot, { requests: [request] });
  return results.length > 0 ? results[0] : null;
}

function resolveMany(ts, projectRoot, request) {
  const requests = Array.isArray(request.requests) ? request.requests : [];
  return requests.map((item) => {
    if (!item || typeof item !== "object") {
      return null;
    }

    const itemProjectRoot = path.resolve(String(item.projectRoot || projectRoot));
    const itemTs = itemProjectRoot === projectRoot ? ts : loadTypescript(itemProjectRoot);
    if (itemTs === null) {
      return null;
    }

    if (item.command === "resolveImport") {
      return resolveImport(itemTs, itemProjectRoot, item);
    }
    if (item.command === "resolveReexport") {
      return resolveReexport(itemTs, itemProjectRoot, item);
    }
    return null;
  });
}

function respondToSessionLine(line) {
  const request = JSON.parse(line);
  const projectRoot = path.resolve(String(request.projectRoot || "."));
  const ts = loadTypescript(projectRoot);

  if (request.command === "checkReturnContracts") {
    return checkReturnContracts(ts, projectRoot, request);
  }

  if (ts === null) {
    if (request.command === "resolveMany") {
      return Array.isArray(request.requests)
        ? request.requests.map(() => null)
        : [];
    }
    return null;
  }

  if (request.command === "resolveImport") {
    return resolveImport(ts, projectRoot, request);
  }
  if (request.command === "resolveReexport") {
    return resolveReexport(ts, projectRoot, request);
  }
  if (request.command === "resolveMany") {
    return resolveMany(ts, projectRoot, request);
  }
  return null;
}

function checkReturnContracts(ts, projectRoot, request) {
  const crypto = require("crypto");
  const source = typeof request.source === "string" ? request.source : "";
  const hash = crypto.createHash("sha256").update(source, "utf8").digest("hex");
  const expectations = Array.isArray(request.expectations) ? request.expectations : [];
  const requestHash = crypto.createHash("sha256").update(JSON.stringify([
    hash, path.resolve(projectRoot, String(request.sourcePath || ".")),
    path.resolve(projectRoot, String(request.configPath || ".")),
    expectations.map(item => [item.name, item.line, item.expectedType]),
  ]), "utf8").digest("hex");
  const result = {
    sourceSha256: hash,
    requestSha256: requestHash,
    compilerVersion: ts ? ts.version : null,
    configPath: null,
    strictNullChecks: null,
    items: expectations.map(item => ({
      name: item.name, line: item.line, status: "unavailable",
      inferredType: null, diagnostics: ["Compiler return proof unavailable"],
    })),
  };
  const fail = message => {
    result.items.forEach(item => { item.diagnostics = [message]; });
    return result;
  };
  if (request.requestSha256 !== undefined && request.requestSha256 !== requestHash) {
    return fail("Request fingerprint mismatch");
  }
  if (!ts) return fail("Local TypeScript SDK is unavailable");
  if (typeof request.source !== "string" || request.sourceSha256 !== hash) {
    return fail("Invalid supplied source or source hash mismatch");
  }
  if (!request.configPath || !request.sourcePath) return fail("Explicit source and owning config are required");
  const configPath = path.resolve(projectRoot, request.configPath);
  const sourcePath = path.resolve(projectRoot, request.sourcePath);
  result.configPath = configPath;
  const config = ts.readConfigFile(configPath, ts.sys.readFile);
  const diagnosticText = diagnostic => ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
  if (config.error) return fail(diagnosticText(config.error));
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, path.dirname(configPath), undefined, configPath);
  if (parsed.errors.length) return fail(parsed.errors.map(diagnosticText).join("\n"));
  if (!parsed.fileNames.some(name => path.resolve(name) === sourcePath)) {
    return fail("Source file is not included in the explicitly supplied owning config");
  }
  if (!/\.tsx?$/.test(sourcePath)) return fail("Return proofs require a TypeScript source file");
  if (parsed.options.noCheck) return fail("Compiler noCheck disables semantic proof checking");
  // Library-check flags are performance shortcuts, not return-type semantics.
  // Disable them so diagnostics cannot skip the requested target file.
  const options = { ...parsed.options, noEmit: true, skipLibCheck: false, skipDefaultLibCheck: false };
  result.strictNullChecks = options.strictNullChecks === undefined ? !!options.strict : !!options.strictNullChecks;
  const kind = sourcePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const original = ts.createSourceFile(sourcePath, source, ts.ScriptTarget.Latest, true, kind);
  if (original.isDeclarationFile) return fail("Declaration files are unsupported for implementation-return proofs");
  if (original.checkJsDirective && !original.checkJsDirective.enabled) {
    return fail("Source @ts-nocheck disables semantic proof checking");
  }
  if (original.parseDiagnostics.length) return fail(original.parseDiagnostics.map(diagnosticText).join("\n"));
  const declarations = original.statements.filter(ts.isFunctionDeclaration);
  const aliases = [];
  const eligible = [];
  let overlay = source + "\n;\n";
  expectations.forEach((expectation, index) => {
    const item = result.items[index];
    const reject = message => { item.diagnostics = [message]; };
    if (typeof expectation.name !== "string" || !Number.isInteger(expectation.line) || expectation.line < 1 || typeof expectation.expectedType !== "string" || !expectation.expectedType.trim()) {
      reject("Invalid declaration identity or expected type"); return;
    }
    const candidates = declarations.filter(node => node.name && node.name.text === expectation.name);
    if (candidates.length !== 1 || !candidates[0].body || candidates[0].type ||
        original.getLineAndCharacterOfPosition(candidates[0].getStart(original)).line + 1 !== expectation.line) {
      reject("Expected one unannotated top-level function declaration at the requested line; overloads are unsupported"); return;
    }
    const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, ts.LanguageVariant.Standard, expectation.expectedType);
    let token;
    let suppressed = false;
    while ((token = scanner.scan()) !== ts.SyntaxKind.EndOfFileToken) {
      if ((token === ts.SyntaxKind.SingleLineCommentTrivia || token === ts.SyntaxKind.MultiLineCommentTrivia) &&
          /@ts-(?:ignore|expect-error|nocheck|check)\b/.test(scanner.getTokenText())) {
        suppressed = true;
      }
    }
    if (suppressed) { reject("Expected type cannot contain checking directives"); return; }
    // Parse the expression alone before placing it in the owning module scope.
    const probe = ts.createSourceFile("expected.ts", "type __expected = " + expectation.expectedType + ";", ts.ScriptTarget.Latest, true);
    if (probe.parseDiagnostics.length || probe.statements.length !== 1 || !ts.isTypeAliasDeclaration(probe.statements[0])) {
      reject("Expected type must be one inert valid type expression"); return;
    }
    let alias = "__maid_return_" + hash + "_" + index;
    while (source.includes(alias)) alias += "_";
    aliases[index] = alias;
    eligible.push(index);
    // Export only for existing external modules; preserve global-script semantics.
    overlay += "\n" + (ts.isExternalModule(original) ? "export " : "") + "type " + alias + " = " + expectation.expectedType + ";\n";
  });
  if (!eligible.length) return result;
  const host = ts.createCompilerHost(options, true);
  const getSourceFile = host.getSourceFile.bind(host);
  host.getSourceFile = (name, ...args) => path.resolve(name) === sourcePath
    ? ts.createSourceFile(sourcePath, overlay, ts.ScriptTarget.Latest, true, kind)
    : getSourceFile(name, ...args);
  const program = ts.createProgram(parsed.fileNames, options, host);
  const target = program.getSourceFile(sourcePath);
  if (!target) return fail("Supplied source is unavailable in the compiler program");
  const diagnostics = [
    ...program.getOptionsDiagnostics(),
    ...program.getSyntacticDiagnostics(target),
    ...program.getSemanticDiagnostics(target),
  ];
  if (diagnostics.length) return fail(diagnostics.map(diagnosticText).join("\n"));
  const checker = program.getTypeChecker();
  const functions = target.statements.filter(ts.isFunctionDeclaration);
  const typeAliases = target.statements.filter(ts.isTypeAliasDeclaration);
  eligible.forEach(index => {
    const item = result.items[index];
    const declaration = functions.find(node => node.name && node.name.text === item.name);
    const alias = typeAliases.find(node => node.name.text === aliases[index]);
    const signature = checker.getSignatureFromDeclaration(declaration);
    if (!signature || !alias) { item.diagnostics = ["Compiler could not identify return type"]; return; }
    const actual = checker.getReturnTypeOfSignature(signature);
    const expected = checker.getTypeFromTypeNode(alias.type);
    if ((actual.flags | expected.flags) & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) {
      item.diagnostics = ["Top-level any, unknown, or error types cannot establish a return contract"]; return;
    }
    item.inferredType = checker.typeToString(actual);
    item.status = checker.isTypeAssignableTo(actual, expected) && checker.isTypeAssignableTo(expected, actual)
      ? "matched" : "mismatched";
    item.diagnostics = [];
  });
  return result;
}

function loadTypescript(projectRoot) {
  const packageJson = findPackageJson(projectRoot) || path.join(projectRoot, "package.json");

  try {
    const projectRequire = moduleApi.createRequire(packageJson);
    return projectRequire("typescript");
  } catch (_error) {
    // Fall through to the bridge environment for MAID Runner's own tests.
  }

  try {
    return require("typescript");
  } catch (_error) {
    return null;
  }
}

function findPackageJson(projectRoot) {
  let current = projectRoot;
  while (true) {
    const candidate = path.join(current, "package.json");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function loadProject(ts, projectRoot, extraRootName) {
  const projectConfig = readProjectConfig(ts, projectRoot);
  const options = projectConfig.options;
  let rootNames = projectConfig.rootNames;

  if (projectConfig.configError) {
    return { options, host: ts.createCompilerHost(options, true), program: null };
  }

  if (extraRootName && !rootNames.includes(extraRootName)) {
    rootNames = rootNames.concat([extraRootName]);
  }

  const host = ts.createCompilerHost(options, true);
  const program = ts.createProgram(rootNames, options, host);
  return { options, host, program };
}

function loadImportResolutionProject(ts, projectRoot, importerFile) {
  const cacheKey = importResolutionProjectCacheKey(ts, projectRoot, importerFile);
  const cached = IMPORT_RESOLUTION_PROJECT_CACHE.get(cacheKey);
  if (cached) {
    return cached;
  }

  const projectConfig = readProjectConfig(ts, projectRoot);
  const project = {
    options: projectConfig.options,
    host: ts.createCompilerHost(projectConfig.options, true),
  };
  IMPORT_RESOLUTION_PROJECT_CACHE.set(cacheKey, project);
  return project;
}

function readProjectConfig(ts, projectRoot) {
  const configPath = ts.findConfigFile(projectRoot, ts.sys.fileExists, "tsconfig.json");
  const defaultOptions = {
    allowJs: true,
    jsx: ts.JsxEmit.ReactJSX,
    moduleResolution: ts.ModuleResolutionKind.Node10,
  };

  if (!configPath) {
    return {
      configPath: null,
      options: defaultOptions,
      rootNames: [],
      configError: false,
    };
  }

  const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
  if (configFile.error) {
    return {
      configPath,
      options: defaultOptions,
      rootNames: [],
      configError: true,
    };
  }

  const parsed = ts.parseJsonConfigFileContent(
    configFile.config,
    ts.sys,
    path.dirname(configPath),
    undefined,
    configPath
  );
  return {
    configPath,
    options: parsed.options,
    rootNames: parsed.fileNames,
    configError: false,
  };
}

function importResolutionProjectCacheKey(ts, projectRoot, importerFile) {
  const configPath = ts.findConfigFile(projectRoot, ts.sys.fileExists, "tsconfig.json");
  return JSON.stringify([
    path.resolve(projectRoot),
    configPath ? path.resolve(configPath) : "",
    configPath ? projectConfigSignature(ts, projectRoot, configPath) : "no-config",
    importerResolutionSignature(projectRoot, importerFile),
  ]);
}

function projectConfigSignature(ts, projectRoot, configPath) {
  const visited = new Set();
  const signatures = [];

  function visit(candidate) {
    const resolved = path.resolve(candidate);
    if (visited.has(resolved)) {
      return;
    }
    visited.add(resolved);
    signatures.push(fileContentSignature(resolved));

    const configFile = ts.readConfigFile(resolved, ts.sys.readFile);
    if (configFile.error || !configFile.config || !configFile.config.extends) {
      return;
    }

    const extendedConfigs = Array.isArray(configFile.config.extends)
      ? configFile.config.extends
      : [configFile.config.extends];
    for (const extendedConfig of extendedConfigs) {
      if (typeof extendedConfig !== "string" || extendedConfig.length === 0) {
        continue;
      }
      const extendedPath = resolveExtendsPath(projectRoot, resolved, extendedConfig);
      if (extendedPath) {
        visit(extendedPath);
      } else {
        signatures.push(`unresolved-extends:${extendedConfig}`);
      }
    }
  }

  visit(configPath);
  return signatures.join("|");
}

function resolveExtendsPath(projectRoot, configPath, extendedConfig) {
  if (extendedConfig.startsWith(".") || path.isAbsolute(extendedConfig)) {
    const candidate = path.resolve(path.dirname(configPath), extendedConfig);
    return withJsonExtension(candidate);
  }

  try {
    const configRequire = moduleApi.createRequire(configPath);
    return configRequire.resolve(extendedConfig);
  } catch (_error) {
    return null;
  }
}

function withJsonExtension(candidate) {
  if (fs.existsSync(candidate)) {
    return candidate;
  }
  if (path.extname(candidate) === "") {
    const jsonCandidate = `${candidate}.json`;
    if (fs.existsSync(jsonCandidate)) {
      return jsonCandidate;
    }
  }
  return candidate;
}

function importerResolutionSignature(projectRoot, importerFile) {
  const importerPath = path.resolve(projectRoot, importerFile);
  const packageJson = nearestPackageJson(projectRoot, path.dirname(importerPath));
  return JSON.stringify([
    path.relative(path.resolve(projectRoot), path.dirname(importerPath)),
    packageJson ? fileContentSignature(packageJson) : "no-package-json",
  ]);
}

function nearestPackageJson(projectRoot, startDir) {
  const absoluteRoot = path.resolve(projectRoot);
  let current = path.resolve(startDir);
  while (isInsideOrEqual(absoluteRoot, current)) {
    const candidate = path.join(current, "package.json");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  return null;
}

function fileContentSignature(fileName) {
  try {
    return `${path.resolve(fileName)}:${fs.readFileSync(fileName, "utf8")}`;
  } catch (_error) {
    return `${path.resolve(fileName)}:<missing>`;
  }
}

function resolveImport(ts, projectRoot, request) {
  const specifier = String(request.specifier || "");
  const importerModule = String(request.importerModule || "");
  if (!specifier || !importerModule) {
    return null;
  }

  const importerFile = moduleFileCandidate(projectRoot, importerModule);
  const project = loadImportResolutionProject(ts, projectRoot, importerFile);
  const resolved = ts.resolveModuleName(
    specifier,
    importerFile,
    project.options,
    project.host
  ).resolvedModule;

  if (!resolved || !resolved.resolvedFileName) {
    return null;
  }

  return moduleIdFromFile(projectRoot, resolved.resolvedFileName, {
    collapseIndex: !specifierTargetsIndex(specifier),
  });
}

function resolveReexport(ts, projectRoot, request) {
  const moduleId = String(request.module || "");
  const name = String(request.name || "");
  if (!moduleId || !name) {
    return null;
  }

  const moduleFile = existingModuleFile(projectRoot, moduleId);
  if (moduleFile === null) {
    return null;
  }

  const project = loadProject(ts, projectRoot, moduleFile);
  if (project.program === null) {
    return null;
  }

  const sourceFile = project.program.getSourceFile(moduleFile);
  if (!sourceFile) {
    return null;
  }

  const checker = project.program.getTypeChecker();
  const moduleSymbol = sourceFile.symbol || checker.getSymbolAtLocation(sourceFile);
  if (!moduleSymbol) {
    return null;
  }

  const exported = checker
    .getExportsOfModule(moduleSymbol)
    .find((symbol) => symbol.getName() === name);
  if (!exported || hasNamespaceExportDeclaration(ts, exported)) {
    return null;
  }

  const target = isAlias(ts, exported) ? checker.getAliasedSymbol(exported) : exported;
  if (!target) {
    return null;
  }

  const declaration = declarationForResolvedSymbol(target, sourceFile);
  if (!declaration) {
    return null;
  }
  if (declaration.getSourceFile().fileName === sourceFile.fileName) {
    return null;
  }

  const resolvedModule = moduleIdFromFile(
    projectRoot,
    declaration.getSourceFile().fileName,
    { collapseIndex: false }
  );
  if (resolvedModule === null) {
    return null;
  }

  return {
    module: resolvedModule,
    name: symbolName(target, declaration, name),
  };
}

function moduleFileCandidate(projectRoot, moduleId) {
  const base = path.resolve(projectRoot, moduleId);
  for (const extension of SOURCE_EXTENSIONS) {
    const candidate = `${base}${extension}`;
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return `${base}.ts`;
}

function existingModuleFile(projectRoot, moduleId) {
  const base = path.resolve(projectRoot, moduleId);
  for (const extension of SOURCE_EXTENSIONS) {
    const candidate = `${base}${extension}`;
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  for (const extension of SOURCE_EXTENSIONS) {
    const candidate = path.join(base, `index${extension}`);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function moduleIdFromFile(projectRoot, fileName, options) {
  const absoluteRoot = path.resolve(projectRoot);
  const absoluteFile = path.resolve(fileName);
  const originalRelative = path.relative(absoluteRoot, absoluteFile);
  const originalInside = isInsideProject(originalRelative);
  const originalInNodeModules = hasPathSegment(originalRelative, "node_modules");

  let selected = null;
  const realFile = realpathOrSelf(absoluteFile);
  const realRelative = path.relative(absoluteRoot, realFile);
  if (isInsideProject(realRelative) && !hasPathSegment(realRelative, "node_modules")) {
    selected = realFile;
  } else if (originalInside && !originalInNodeModules) {
    selected = absoluteFile;
  }

  if (selected === null) {
    return null;
  }

  let relative = path.relative(absoluteRoot, selected);
  relative = stripSourceExtension(relative);

  if (options.collapseIndex && path.basename(relative) === "index") {
    relative = path.dirname(relative);
  }

  return toPosix(relative);
}

function stripSourceExtension(value) {
  for (const extension of SOURCE_EXTENSIONS) {
    if (value.endsWith(extension)) {
      return value.slice(0, -extension.length);
    }
  }
  return value;
}

function specifierTargetsIndex(specifier) {
  const trimmed = specifier.replace(/\/+$/, "");
  const base = trimmed.slice(trimmed.lastIndexOf("/") + 1);
  return stripSourceExtension(base) === "index";
}

function isInsideProject(relativePath) {
  return (
    relativePath !== "" &&
    !relativePath.startsWith("..") &&
    !path.isAbsolute(relativePath)
  );
}

function isInsideOrEqual(root, candidate) {
  return root === candidate || isInsideProject(path.relative(root, candidate));
}

function hasPathSegment(value, segment) {
  return value.split(path.sep).includes(segment);
}

function realpathOrSelf(fileName) {
  try {
    return fs.realpathSync(fileName);
  } catch (_error) {
    return fileName;
  }
}

function isAlias(ts, symbol) {
  return (symbol.flags & ts.SymbolFlags.Alias) !== 0;
}

function hasNamespaceExportDeclaration(ts, symbol) {
  return (symbol.declarations || []).some(
    (declaration) => declaration.kind === ts.SyntaxKind.NamespaceExport
  );
}

function declarationForResolvedSymbol(symbol, barrelSourceFile) {
  const declarations = symbol.declarations || [];
  return (
    declarations.find(
      (declaration) => declaration.getSourceFile().fileName !== barrelSourceFile.fileName
    ) ||
    declarations.find((declaration) => declaration.getSourceFile().fileName)
  );
}

function symbolName(symbol, declaration, requestedName) {
  if (declaration.name && typeof declaration.name.getText === "function") {
    const declaredName = declaration.name.getText();
    if (declaredName && declaredName !== "default") {
      return declaredName;
    }
  }

  const name = symbol.getName();
  if (name && name !== "default" && name !== "__export") {
    return name;
  }
  return requestedName;
}

function toPosix(value) {
  return value.split(path.sep).join("/");
}

if (require.main === module) {
  if (process.argv.includes("--session")) {
    const rl = readline.createInterface({
      input: process.stdin,
      crlfDelay: Infinity,
    });
    rl.on("line", (line) => {
      try {
        const result = respondToSessionLine(line);
        process.stdout.write(`${JSON.stringify({ ok: true, result })}\n`);
      } catch (error) {
        process.stdout.write(
          `${JSON.stringify({
            ok: false,
            error: error && error.message ? error.message : String(error),
          })}\n`
        );
      }
    });
  } else {
    try {
      const result = main();
      process.stdout.write(JSON.stringify({ ok: true, result }));
    } catch (error) {
      process.stdout.write(
        JSON.stringify({
          ok: false,
          error: error && error.message ? error.message : String(error),
        })
      );
    }
  }
}

module.exports = {
  main,
  resolveMany,
  resolveImport,
  resolveReexport,
};
