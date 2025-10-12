const fs = require('fs');
const path = require('path');

const nodeModulesPath = path.join(process.cwd(), 'node_modules');
const pnpmMarkerPath = path.join(nodeModulesPath, '.pnpm');

if (fs.existsSync(pnpmMarkerPath)) {
  console.log('Detected pnpm-managed node_modules; removing before npm install.');
  fs.rmSync(nodeModulesPath, { recursive: true, force: true });
}
