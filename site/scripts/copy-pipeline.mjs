#!/usr/bin/env node
/**
 * copy-pipeline.mjs - stage the subset of pipeline/ that api/generate.py
 * needs inside site/ before the build.
 *
 * Vercel's Root Directory is set to site/. Its Python builder does not
 * bundle files from outside the Root Directory into a deployed function
 * automatically - not even with "Include source files outside of the Root
 * Directory in the Build Step" enabled (that setting only grants *read*
 * access during the build step; it doesn't make includeFiles resolve a
 * "../" path into the runtime bundle - confirmed by testing, this does NOT
 * work: the deployed function still couldn't find pipeline/ at runtime).
 *
 * This script instead copies the needed pipeline/ files to site/pipeline/
 * before the Astro build runs, so they're ordinary files inside Root
 * Directory by the time Vercel's Python builder scans for what to bundle -
 * no includeFiles glob required. site/pipeline/ is build-time-only output
 * (gitignored); the repo-root pipeline/ remains the single source of
 * truth. See api/generate.py's _find_pipeline_dir(), which walks up from
 * itself looking for a "pipeline" directory and finds this copy first,
 * falling back to the real repo-root pipeline/ during local development
 * when this script hasn't been run.
 *
 * Deliberately an allowlist, not a denylist: pipeline/ is a shared
 * directory that can grow local-only content over time (e.g. a .venv/
 * virtualenv, which is exactly what a denylist here missed once already -
 * it got copied wholesale before this was caught). Only copy what
 * api/generate.py's import chain (research, image_reviewer,
 * content_generator, config, net) actually needs at runtime.
 *
 * Deliberately does NOT delete site/pipeline/ before copying: each target
 * file is overwritten in place instead. A prior version wiped the whole
 * directory first and could fail if a stray file there (e.g. a Python
 * __pycache__ .pyc from local testing) couldn't be removed - overwriting
 * known files avoids needing to delete anything at all.
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = path.dirname(siteDir);
const source = path.join(repoRoot, "pipeline");
const dest = path.join(siteDir, "pipeline");

if (!existsSync(source)) {
  console.error(`copy-pipeline: source directory not found: ${source}`);
  process.exit(1);
}

// Only the modules api/generate.py's import chain actually touches at
// runtime (research, image_reviewer, content_generator, plus their shared
// config/net helpers) - not the CLI-only modules (main.py, tiktok_auth.py,
// instagram_auth.py, social_media.py, species_selector.py,
// video_generator.py) or dev-only content (evals/, data/eval_fixture.json,
// .venv/, output/, __pycache__, lockfiles).
const FILES = [
  "config.py",
  "research.py",
  "content_generator.py",
  "image_reviewer.py",
  "net.py",
];
// Data files content_generator.py reads at request time
// (config.DATA_DIR / "hashtags.json").
const DATA_FILES = ["hashtags.json"];

mkdirSync(dest, { recursive: true });
for (const file of FILES) {
  const from = path.join(source, file);
  if (!existsSync(from)) {
    console.error(`copy-pipeline: expected file missing: ${from}`);
    process.exit(1);
  }
  cpSync(from, path.join(dest, file));
}

mkdirSync(path.join(dest, "data"), { recursive: true });
for (const file of DATA_FILES) {
  const from = path.join(source, "data", file);
  if (!existsSync(from)) {
    console.error(`copy-pipeline: expected data file missing: ${from}`);
    process.exit(1);
  }
  cpSync(from, path.join(dest, "data", file));
}

console.log(
  `copy-pipeline: copied ${FILES.length} module(s) and ${DATA_FILES.length} data file(s) from ${source} -> ${dest}`,
);
