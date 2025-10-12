const fs = require('fs');
const path = require('path');

const userAgent = process.env.npm_config_user_agent || '';
const isNpm = userAgent.startsWith('npm/');

if (!isNpm) {
  // The cleanup is only required for npm installs: pnpm and other package managers
  // already handle their own node_modules layouts and should not be disturbed.
  return;
}

const nodeModulesPath = path.join(process.cwd(), 'node_modules');
const pnpmMarkerPath = path.join(nodeModulesPath, '.pnpm');

if (fs.existsSync(pnpmMarkerPath)) {
  console.log('Detected pnpm-managed node_modules; removing before npm install.');
  fs.rmSync(nodeModulesPath, { recursive: true, force: true });
}
