#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const docs = path.join(root, "docs");
const current = path.join(docs, "current");

const PORTAL_ARTIFACTS = ["index.html", "index.json", "docs-map.json", "release-manifest.json"];
const PORTAL_JSON = ["index.json", "docs-map.json", "release-manifest.json"];

function checksumFor(mdFile) {
  return crypto.createHash("sha256").update(fs.readFileSync(mdFile)).digest("hex");
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function canonicalFiles() {
  return fs.readdirSync(current).filter((f) => f.endsWith(".md"));
}

function inspect() {
  const fail = [];
  const staleChecksums = [];
  const missingCounterparts = [];
  const files = canonicalFiles();

  for (const f of files) {
    const slug = f.slice(0, -3);
    const md = path.join(current, f);
    const html = path.join(current, slug + ".html");
    const jsonFile = path.join(current, slug + ".json");

    if (!fs.existsSync(html) || !fs.existsSync(jsonFile)) {
      fail.push(`${slug}: missing counterpart`);
      missingCounterparts.push(slug);
      continue;
    }

    let meta;
    try {
      meta = readJson(jsonFile);
    } catch {
      fail.push(`${slug}: invalid JSON`);
      continue;
    }

    const sum = checksumFor(md);
    if (meta.sourceChecksum !== sum) {
      fail.push(`${slug}: stale checksum`);
      staleChecksums.push(slug);
    }
    if (meta.sourceOfTruth !== `current/${slug}.md`) {
      fail.push(`${slug}: wrong source path`);
    }

    const page = fs.readFileSync(html, "utf8");
    for (const token of [
      "<header",
      "<nav",
      "<main",
      "<article",
      "<footer",
      `${slug}.md`,
      `${slug}.json`,
    ]) {
      if (!page.includes(token)) fail.push(`${slug}: HTML missing ${token}`);
    }
  }

  for (const f of PORTAL_ARTIFACTS) {
    if (!fs.existsSync(path.join(docs, f))) fail.push(`missing ${f}`);
  }

  for (const f of PORTAL_JSON) {
    try {
      readJson(path.join(docs, f));
    } catch {
      fail.push(`invalid ${f}`);
    }
  }

  const map = fs.readFileSync(path.join(docs, "docs-map.json"), "utf8");
  for (const f of files) {
    const slug = f.slice(0, -3);
    if (!map.includes(`"${slug}"`)) fail.push(`${slug}: missing docs map entry`);
  }

  return { fail, files, staleChecksums, missingCounterparts };
}

function reportStale({ files, staleChecksums, missingCounterparts }) {
  if (staleChecksums.length === 0 && missingCounterparts.length === 0) {
    console.log(
      `No refresh is needed: ${files.length} canonical guides already match their HTML and JSON counterparts.`,
    );
  } else {
    console.log(
      `Counterparts needing regeneration: ${staleChecksums.length + missingCounterparts.length} of ${files.length} canonical guides.`,
    );
    if (staleChecksums.length > 0) {
      console.log(`- stale sourceChecksum: ${staleChecksums.join(", ")}`);
    }
    if (missingCounterparts.length > 0) {
      console.log(`- missing counterpart: ${missingCounterparts.join(", ")}`);
    }
  }
}

function runCheck() {
  const { fail, files } = inspect();
  if (fail.length) {
    console.error("Documentation check failed:\n- " + fail.join("\n- "));
    process.exit(1);
  }
  console.log(`Documentation check passed: ${files.length} canonical guides with HTML and JSON counterparts.`);
}

function runBuild() {
  const inspected = inspect();
  console.error("docs:build is not a generator in this repository.");
  console.error(
    "The HTML/JSON counterparts and portal artifacts under docs/ were produced by the upstream docs",
  );
  console.error(
    "packaging pipeline. That generator is not vendored here, so there is nothing this script can",
  );
  console.error(
    "honestly regenerate: reporting success here would falsely claim that stale artifacts were rebuilt.",
  );
  console.error("");
  console.error("To refresh documentation after editing docs/current/*.md:");
  console.error("1. Regenerate the HTML/JSON counterparts and refresh each sourceChecksum with the");
  console.error("   upstream docs packaging pipeline (the script that produced docs/index.html,");
  console.error("   docs/docs-map.json, and docs/release-manifest.json).");
  console.error("2. Re-run `bun run docs:check`, which is the supported gate.");
  console.error("");
  reportStale(inspected);
  process.exit(1);
}

const command = process.argv[2] || "check";

if (command === "check") {
  runCheck();
} else if (command === "build") {
  runBuild();
} else {
  console.error(`Unknown command: ${command}`);
  console.error("Usage: node scripts/docs.mjs <check|build>");
  console.error("  check  validate docs/current counterparts, checksums, and portal artifacts");
  console.error("  build  not implemented here; exits non-zero with remediation steps");
  process.exit(1);
}
