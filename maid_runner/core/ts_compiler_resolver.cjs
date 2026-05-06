"use strict";

const fs = require("fs");
const moduleApi = require("module");
const path = require("path");

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

function main() {
  const raw = fs.readFileSync(0, "utf8");
  const request = JSON.parse(raw);
  const projectRoot = path.resolve(String(request.projectRoot || "."));
  const ts = loadTypescript(projectRoot);

  if (ts === null) {
    return null;
  }

  if (request.command === "resolveImport") {
    return resolveImport(ts, projectRoot, request);
  }
  if (request.command === "resolveReexport") {
    return resolveReexport(ts, projectRoot, request);
  }
  return null;
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
  const configPath = ts.findConfigFile(projectRoot, ts.sys.fileExists, "tsconfig.json");
  let options = {
    allowJs: true,
    jsx: ts.JsxEmit.ReactJSX,
    moduleResolution: ts.ModuleResolutionKind.Node10,
  };
  let rootNames = [];

  if (configPath) {
    const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
    if (configFile.error) {
      return { options, host: ts.createCompilerHost(options, true), program: null };
    }
    const parsed = ts.parseJsonConfigFileContent(
      configFile.config,
      ts.sys,
      path.dirname(configPath),
      undefined,
      configPath
    );
    options = parsed.options;
    rootNames = parsed.fileNames;
  }

  if (extraRootName && !rootNames.includes(extraRootName)) {
    rootNames = rootNames.concat([extraRootName]);
  }

  const host = ts.createCompilerHost(options, true);
  const program = ts.createProgram(rootNames, options, host);
  return { options, host, program };
}

function resolveImport(ts, projectRoot, request) {
  const specifier = String(request.specifier || "");
  const importerModule = String(request.importerModule || "");
  if (!specifier || !importerModule) {
    return null;
  }

  const importerFile = moduleFileCandidate(projectRoot, importerModule);
  const project = loadProject(ts, projectRoot, importerFile);
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
