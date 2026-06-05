// Idempotent setup for the local stdio MCP servers used by Claude Code.
//
// What it does:
//   1. Installs/updates the npm-based MCP servers globally (one registry hit,
//      not one per launch).
//   2. Resolves each server's real entry and writes its launch command into
//      BOTH config files Claude Code may read (~/.claude.json and
//      ~/.claude/mcp.json), keeping everything else intact.
//   3. Ensures the Headroom proxy is up (the headroom MCP server talks to it).
//   4. Verifies every server with a real MCP handshake and prints its tools +
//      the time-to-first-response, so a regression (slow start -> 30s timeout)
//      is visible immediately.
//
// Why `node <entry>` instead of `npx`: `npx -y` re-checks the registry on every
// launch (12-15s here, and worse under the concurrent startup of a fresh
// session), blowing past Claude Code's 30s connection timeout. A direct launch
// of the already-installed package starts in ~3-5s, deterministically.
//
// Run:  node scripts/setup_mcp.mjs        (or: scripts\setup_mcp.ps1)
// Then restart Claude Code so it re-reads the config.

import { execSync, spawn } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';
import http from 'node:http';

const HOME = homedir();
const REPO = dirname(dirname(fileURLToPath(import.meta.url)));
const VENV_PY = join(REPO, '.venv', 'Scripts', 'python.exe');
const TARGETS = [join(HOME, '.claude.json'), join(HOME, '.claude', 'mcp.json')];
const PROXY_PORT = 8787;
const WITH_HEADROOM = process.argv.includes('--with-headroom');
// Keys this script owns: any of these not in the desired set are pruned from
// the config, so dropping a server here removes it from both config files.
const MANAGED = ['sequential-thinking', 'context7', 'headroom'];

// npm-installed stdio MCP servers. Add new ones here and re-run.
const PACKAGES = [
  { server: 'sequential-thinking', pkg: '@modelcontextprotocol/server-sequential-thinking' },
  { server: 'context7', pkg: '@upstash/context7-mcp' },
];

const log = (...a) => console.log(...a);
const sh = (cmd) => execSync(cmd, { encoding: 'utf8' }).trim();

function isInstalled(globalRoot, pkg) {
  return existsSync(join(globalRoot, ...pkg.split('/'), 'package.json'));
}

function distEntry(globalRoot, pkg) {
  const pkgDir = join(globalRoot, ...pkg.split('/'));
  const meta = JSON.parse(readFileSync(join(pkgDir, 'package.json'), 'utf8'));
  let rel = typeof meta.bin === 'string' ? meta.bin : Object.values(meta.bin || {})[0] || meta.main;
  if (!rel) throw new Error(`${pkg}: no bin/main in package.json`);
  const entry = join(pkgDir, rel);
  if (!existsSync(entry)) throw new Error(`${pkg}: entry not found at ${entry}`);
  return entry;
}

function ensureInstalled(globalRoot) {
  const missing = PACKAGES.filter((p) => !isInstalled(globalRoot, p.pkg));
  if (missing.length === 0) { log('  all npm packages already installed globally'); return; }
  const list = missing.map((p) => p.pkg).join(' ');
  log(`  installing globally: ${list}`);
  execSync(`npm i -g ${list}`, { stdio: 'inherit' });
}

// Headroom's MCP server imports the Python MCP SDK, whose jsonschema[format]
// pulls in rfc3987-syntax — an optional URI-format validator that costs ~15s
// just to import and is never needed for MCP schema validation. Removing it
// roughly halves headroom's cold start (~30s -> ~16s), keeping it inside the
// connection timeout. Best-effort and idempotent.
function trimHeadroomStartup() {
  if (!existsSync(VENV_PY)) return;
  try {
    execSync(`"${VENV_PY}" -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('rfc3987_syntax') else 1)"`);
    log('  trimming rfc3987-syntax (slow optional jsonschema format dep)');
    execSync(`"${VENV_PY}" -m pip uninstall -y rfc3987-syntax`, { stdio: 'ignore' });
  } catch {
    log('  rfc3987-syntax already absent (headroom start already trimmed)');
  }
}

function buildMcpServers(globalRoot) {
  const servers = {};
  for (const { server, pkg } of PACKAGES) {
    servers[server] = { command: 'node', args: [distEntry(globalRoot, pkg)] };
  }
  // Headroom MCP server is OFF by default: even after trimming its imports it
  // needs 15-20s to start solo and >60s under the concurrent load of a fresh
  // Claude Code session, which blows the MCP client's hard ~60s request timeout
  // (-32001) that MCP_TIMEOUT does not raise. Opt in with --with-headroom only
  // if you accept that it often fails to attach. The proxy stays useful on its
  // own (route traffic via ANTHROPIC_BASE_URL=http://127.0.0.1:8787).
  if (WITH_HEADROOM && existsSync(VENV_PY)) {
    servers.headroom = {
      command: VENV_PY,
      args: ['-c', 'from headroom.cli import main; main()', 'mcp', 'serve'],
      env: { HEADROOM_REQUIRE_RUST_CORE: 'false' },
    };
  }
  return servers;
}

function writeTarget(file, mcpServers) {
  let obj = { mcpServers: {} };
  if (existsSync(file)) {
    obj = JSON.parse(readFileSync(file, 'utf8'));
    copyFileSync(file, file + '.bak-mcpsetup');
  } else {
    mkdirSync(dirname(file), { recursive: true });
  }
  obj.mcpServers = { ...(obj.mcpServers || {}), ...mcpServers };
  // Prune managed servers that are no longer desired (e.g. headroom when off).
  for (const k of MANAGED) if (!(k in mcpServers) && k in obj.mcpServers) delete obj.mcpServers[k];
  writeFileSync(file, JSON.stringify(obj, null, 2) + '\n');
  log(`  wrote ${file}`);
}

function proxyHealthy() {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port: PROXY_PORT, path: '/livez', timeout: 2500 }, (res) => {
      let b = ''; res.on('data', (d) => b += d);
      res.on('end', () => { try { resolve(JSON.parse(b).alive === true); } catch { resolve(false); } });
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

async function ensureProxy() {
  if (await proxyHealthy()) { log(`  proxy already healthy on :${PROXY_PORT}`); return true; }
  if (!existsSync(VENV_PY)) { log('  venv python missing — cannot start proxy'); return false; }
  log('  starting Headroom proxy (detached) ...');
  const p = spawn(VENV_PY, ['-c', 'from headroom.cli import main; main()', 'proxy', '--port', String(PROXY_PORT), '--no-telemetry'],
    { detached: true, stdio: 'ignore', env: { ...process.env, HEADROOM_REQUIRE_RUST_CORE: 'false' } });
  p.unref();
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    if (await proxyHealthy()) { log(`  proxy ready after ${i + 1}s`); return true; }
  }
  log('  proxy did not become healthy within 30s');
  return false;
}

function handshake(server, cfg, hardLimit = 30000) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const env = cfg.env ? { ...process.env, ...cfg.env } : process.env;
    const p = spawn(cfg.command, cfg.args, { shell: false, env });
    let buf = '', initMs = null, tools = null;
    p.stdout.on('data', (d) => {
      buf += d;
      for (const line of buf.split('\n')) {
        try {
          const j = JSON.parse(line);
          if (j.id === 1 && initMs === null) initMs = Date.now() - t0;
          if (j.id === 2 && j.result?.tools) tools = j.result.tools.map((t) => t.name);
        } catch {}
      }
    });
    p.on('error', (e) => resolve({ server, ok: false, error: e.code }));
    const send = (o) => { try { p.stdin.write(JSON.stringify(o) + '\n'); } catch {} };
    setTimeout(() => {
      send({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'setup', version: '1' } } });
      send({ jsonrpc: '2.0', method: 'notifications/initialized' });
      send({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
    }, 150);
    const iv = setInterval(() => { if (tools) { clearInterval(iv); p.kill(); resolve({ server, ok: true, ms: initMs, tools }); } }, 100);
    setTimeout(() => { clearInterval(iv); p.kill(); resolve({ server, ok: false, error: `no response in ${hardLimit}ms` }); }, hardLimit);
  });
}

(async () => {
  log('MCP setup for Claude Code\n');
  log('node:', process.version, '| npm:', sh('npm -v'));
  const globalRoot = sh('npm root -g');
  log('global node_modules:', globalRoot);
  log('repo:', REPO, '\n');

  log('1) npm packages');
  ensureInstalled(globalRoot);

  log('\n2) config files');
  const mcpServers = buildMcpServers(globalRoot);
  for (const f of TARGETS) writeTarget(f, mcpServers);

  let proxyUp = false;
  if (WITH_HEADROOM) {
    log('\n3) headroom proxy + startup trim');
    trimHeadroomStartup();
    proxyUp = await ensureProxy();
  } else {
    log('\n3) headroom: OFF (pass --with-headroom to enable; see note in buildMcpServers)');
  }

  log('\n4) verify (real MCP handshake)');
  let allOk = true;
  for (const [server, cfg] of Object.entries(mcpServers)) {
    if (server === 'headroom' && !proxyUp) { log(`  SKIP headroom (proxy down)`); continue; }
    const r = await handshake(server, cfg);
    if (r.ok) log(`  OK   ${server}: ${r.ms}ms -> [${r.tools.join(', ')}]`);
    else { allOk = false; log(`  FAIL ${server}: ${r.error}`); }
  }

  log('\n' + (allOk ? 'All servers healthy.' : 'Some servers failed — see above.'));
  log('To keep headroom working across reboots, register the proxy logon task once:');
  log('  scripts\\start_headroom_proxy.ps1 -InstallTask');
  log('Then restart Claude Code so it re-reads the config (tools appear as mcp__<server>__*).');
  process.exit(allOk ? 0 : 1);
})();
