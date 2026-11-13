const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const publish = require('./release.cjs');

// All clients, releases and assets below are synthetic and remain in memory.
module.exports = async () => {
  const version = fs.readFileSync('pyproject.toml', 'utf8').match(/^version = "([^"\r\n]+)"\r?$/m)?.[1];
  assert.ok(version);
  const sha = 'a'.repeat(40);
  const context = { eventName: 'push', ref: 'refs/heads/main', sha,
    repo: { owner: 'fixture', repo: 'fixture' } };
  const messages = [];
  const core = { info: message => messages.push(message) };
  const noWrite = { rest: { repos: { listReleases() {} } },
    paginate: async () => [{ tag_name: 'v' + version, draft: false }] };
  await publish({ github: noWrite, context, core });
  assert.ok(messages.some(message => message.includes('already published; leaving it unchanged')));
  await assert.rejects(publish({ github: noWrite, context: { ...context, eventName: 'pull_request' }, core }));

  let release = null;
  let tag = null;
  let head = sha;
  const assets = [];
  const repos = {
    listReleases() {}, listReleaseAssets() {},
    getBranch: async () => ({ data: { commit: { sha: head } } }),
    createRelease: async args => ({ data: (release = { ...args, id: 1 }) }),
    getRelease: async () => ({ data: release }),
    updateRelease: async args => ({ data: (release = { ...release, ...args }) }),
    uploadReleaseAsset: async args => {
      const asset = { name: args.name, state: 'uploaded', size: args.data.length,
        digest: 'sha256:' + crypto.createHash('sha256').update(args.data).digest('hex') };
      assets.push(asset);
      return { data: asset };
    },
  };
  const git = {
    getRef: async () => {
      if (!tag) throw Object.assign(new Error('fixture tag missing'), { status: 404 });
      return { data: { object: { type: 'commit', sha: tag } } };
    },
    createRef: async args => { tag = args.sha; },
  };
  const github = { rest: { repos, git }, paginate: async method => {
    if (method === repos.listReleases) return release ? [release] : [];
    if (method === repos.listReleaseAssets) return assets;
    throw new Error('Unexpected fixture pagination call');
  } };
  head = 'b'.repeat(40);
  await assert.rejects(publish({ github, context, core }), /Main advanced/);
  assert.equal(release, null);
  head = sha;
  tag = 'b'.repeat(40);
  await assert.rejects(publish({ github, context, core }), /different commit/);
  assert.equal(release, null);
  tag = null;
  await publish({ github, context, core });
  assert.equal(tag, sha);
  assert.equal(release.draft, false);
  assert.deepEqual(assets.map(asset => asset.name).sort(), [
    'SHA256SUMS', `bugbix-${version}-py3-none-any.whl`,
    `bugbix-${version}-py3-none-any.whl.sha256`, `bugbix-${version}.tar.gz`,
    `bugbix-${version}.tar.gz.sha256`,
  ].sort());
};
