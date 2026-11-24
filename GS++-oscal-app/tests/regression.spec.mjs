import crypto from 'node:crypto';
import { test, expect } from '@playwright/test';

const sha256 = (str) => crypto.createHash('sha256').update(str, 'utf8').digest('hex');

// Block external internet calls so tests are 100% deterministic & offline
async function blockExternal(page) {
  await page.route('**/*', (route) => {
    const url = route.request().url();
    if (url.startsWith('http://127.0.0.1:') || url.startsWith('http://localhost:') || url.startsWith('data:') || url.startsWith('blob:')) {
      return route.continue();
    }
    return route.abort();
  });
}

test('#1 Komponentenbezogener SSP -> AR -> Reimport -> POA&M Roundtrip', async ({ page }) => {
  await blockExternal(page);
  await page.goto('/pruefung_ap_ar.html');

  const compA = '11111111-1111-4111-8111-111111111111';
  const compB = '22222222-2222-4222-8222-222222222222';
  const ctrlId = 'SYS.1.1.A1';

  const sampleSSP = {
    'system-security-plan': {
      uuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      metadata: { title: 'Test-SSP', version: '1.0', 'last-modified': '2026-01-01T00:00:00Z', 'oscal-version': '1.2.2' },
      'import-profile': { href: '#prof-1' },
      'system-characteristics': {
        'system-ids': [{ id: 'sys-1' }],
        'system-name': 'Test-System',
        description: 'Test',
        'security-sensitivity-level': 'normal',
        'system-information': { 'information-types': [] },
        status: { state: 'operational' },
        'authorization-boundary': { description: 'Test' },
      },
      'system-implementation': {
        users: [],
        components: [
          { uuid: compA, type: 'software', title: 'Komponente A', description: 'A', status: { state: 'operational' } },
          { uuid: compB, type: 'software', title: 'Komponente B', description: 'B', status: { state: 'operational' } },
        ],
      },
      'control-implementation': {
        description: 'Test',
        'implemented-requirements': [
          {
            uuid: '33333333-3333-4333-8333-333333333333',
            'control-id': ctrlId,
            'by-components': [
              { uuid: '44444444-4444-4444-8444-444444444444', 'component-uuid': compA, description: 'Umgesetzt auf A', 'implementation-status': { state: 'implemented' } },
              { uuid: '55555555-5555-4555-8555-555555555555', 'component-uuid': compB, description: 'Fehlt auf B', 'implementation-status': { state: 'implemented' } },
            ],
          },
        ],
      },
    },
  };

  // Seed SSP in shared workspace set and reload pruefung_ap_ar.html
  await page.evaluate(async (ssp) => {
    await gppArtefacts.save({ stage: 'fill', kind: 'ssp', title: 'Test-SSP', filename: 'test-ssp.json', tool: 'test', data: ssp });
  }, sampleSSP);
  await page.reload();
  await expect(page.locator('#ssp-status')).toContainText('Test-System');

  // Rate same control differently on Component A (satisfied) vs Component B (not-satisfied)
  const arResult = await page.evaluate(async ({ ctrlId, compA, compB }) => {
    window.setF(ctrlId, compA, 'status', 'satisfied');
    window.setF(ctrlId, compA, 'remarks', 'Auf Komponente A vollständig erfüllt');
    window.setF(ctrlId, compB, 'status', 'not-satisfied');
    window.setF(ctrlId, compB, 'remarks', 'Auf Komponente B mangelhaft');

    const built = buildAR();
    const exportedAr = built.doc;
    const findings = exportedAr['assessment-results'].results[0].findings;

    // Persist AR to workspace set (for POA&M generator)
    await gppArtefacts.save({ stage: 'assess', kind: 'ar', title: 'Test-AR', filename: 'test-ar.json', tool: 'pruefung_ap_ar', data: exportedAr });

    // Clear and re-import AR to verify per-component roundtrip fidelity
    S.findings.clear();
    await hydrateFromAR(exportedAr);
    const fA = getFinding(ctrlId, compA);
    const fB = getFinding(ctrlId, compB);

    // Also test legacy fallback: AR without component-uuid prop
    const legacyAr = JSON.parse(JSON.stringify(exportedAr));
    legacyAr['assessment-results'].results[0].findings = [
      {
        uuid: '99999999-9999-4999-8999-999999999999',
        title: 'Legacy',
        description: 'Legacy-Befund ohne Komponenten-UUID',
        target: { type: 'objective-id', 'target-id': ctrlId, status: { state: 'not-satisfied', reason: 'Legacy-Grund' } },
      },
    ];
    S.findings.clear();
    await hydrateFromAR(legacyAr);
    const legacyA = getFinding(ctrlId, compA);
    const legacyB = getFinding(ctrlId, compB);

    return { exportedAr, findings, fA, fB, legacyA, legacyB };
  }, { ctrlId, compA, compB });

  expect(arResult.findings).toHaveLength(2);
  const byComp = Object.fromEntries(
    arResult.findings.map(f => [
      (f.props || []).find(p => p.name === 'component-uuid')?.value,
      f.target.status.state,
    ])
  );
  expect(byComp[compA]).toBe('satisfied');
  expect(byComp[compB]).toBe('not-satisfied');

  // Reimport preserved distinct verdicts per component
  expect(arResult.fA.status).toBe('satisfied');
  expect(arResult.fA.remarks).toContain('Komponente A');
  expect(arResult.fB.status).toBe('not-satisfied');
  expect(arResult.fB.remarks).toContain('Komponente B');

  // Legacy AR fallback still maps cleanly
  expect(arResult.legacyA.status).toBe('not-satisfied');
  expect(arResult.legacyB.status).toBe('not-satisfied');

  // Navigate to abarbeiten_POAM_generator.html — auto-imports the AR from gppArtefacts (no observations!)
  await page.goto('/abarbeiten_POAM_generator.html');
  await page.waitForFunction(() => typeof P !== 'undefined' && Array.isArray(P.items) && P.items.length > 0);
  const poamCheck = await page.evaluate(() => P.items.map(it => ({
    controlId: it.controlId,
    componentUuid: it.componentUuid,
    component: it.component,
  })));

  // Only Component B (not-satisfied) should become a POA&M item, with compB UUID intact!
  expect(poamCheck).toHaveLength(1);
  expect(poamCheck[0].controlId).toBe(ctrlId);
  expect(poamCheck[0].componentUuid).toBe(compB);
});

test('#2 XSS-Schutz im Viewer (Cache, frische Antwort, Fallback) + Session-Storage-Default + SRI', async ({ page }) => {
  await blockExternal(page);
  await page.goto('/GSpp-Viewer.html');

  const xssRes = await page.evaluate(() => {
    window.__xssTriggered = 0;
    const evilMd = [
      '# Titel',
      '<img src=x onerror="window.__xssTriggered=1">',
      '<script>window.__xssTriggered=2</script>',
      '<iframe src="https://evil.example"></iframe>',
      '<a href="javascript:window.__xssTriggered=3">Klick</a>',
    ].join('\n\n');

    // 1. Test gppRenderMarkdown WITH a mocked marked.parse that returns raw HTML (exercises gppSanitizeHtml!)
    const origMarked = window.marked;
    window.marked = { parse: (s) => `<h1>Titel</h1><img src=x onerror="window.__xssTriggered=1"><script>window.__xssTriggered=2</script><iframe src="https://evil.example"></iframe><a href="javascript:window.__xssTriggered=3">Klick</a>` };
    const htmlSanitized = gppRenderMarkdown(evilMd);
    const box1 = document.createElement('div');
    box1.innerHTML = htmlSanitized;
    document.body.appendChild(box1);

    // 2. Test fallback explicitly with marked disabled (must HTML-escape everything!)
    window.marked = undefined;
    const htmlFallback = gppRenderMarkdown(evilMd);
    window.marked = origMarked;
    const box2 = document.createElement('div');
    box2.innerHTML = htmlFallback;
    document.body.appendChild(box2);

    // 3. Test sessionStorage default for secrets in gppCfg
    localStorage.clear();
    sessionStorage.clear();
    gppCfg.set('ai:key:gemini', 'AIza-secret-test');
    gppCfg.set('gh:token', 'ghp_secret_test');
    const inLocalDefault = {
      gemini: localStorage.getItem('gpp:cfg:ai:key:gemini'),
      gh: localStorage.getItem('gpp:cfg:gh:token'),
    };
    const inSessionDefault = {
      gemini: sessionStorage.getItem('gpp:cfg:ai:key:gemini'),
      gh: sessionStorage.getItem('gpp:cfg:gh:token'),
    };
    const readBack = {
      gemini: gppCfg.get('ai:key:gemini'),
      gh: gppCfg.get('gh:token'),
    };

    // Opt-in localStorage persistence
    gppCfg.setPersistSecrets(true);
    const inLocalOptIn = localStorage.getItem('gpp:cfg:ai:key:gemini');
    // Opt-out removes from localStorage again
    gppCfg.setPersistSecrets(false);
    const inLocalAfterOff = localStorage.getItem('gpp:cfg:ai:key:gemini');

    // 4. Verify SRI hashes in GPP_LIBS and marked <script> tag
    const markedScript = Array.from(document.querySelectorAll('script[src]')).find(s => s.src.includes('marked'));
    const sriCheck = {
      ...Object.fromEntries(
        Object.entries(GPP_LIBS).map(([k, v]) => [k, Boolean(v.integrity && v.integrity.startsWith('sha384-'))])
      ),
      marked: Boolean(markedScript && markedScript.integrity && markedScript.integrity.startsWith('sha384-') && markedScript.crossOrigin === 'anonymous'),
    };

    return {
      xssTriggered: window.__xssTriggered,
      dangerousEls1: box1.querySelectorAll('script, iframe, [onerror], [onclick], a[href^="javascript:"]').length,
      hasHeading1: box1.querySelectorAll('h1').length,
      dangerousEls2: box2.querySelectorAll('script, iframe, img, [onerror], a').length,
      inLocalDefault,
      inSessionDefault,
      readBack,
      inLocalOptIn,
      inLocalAfterOff,
      sriCheck,
    };
  });

  expect(xssRes.xssTriggered).toBe(0);
  expect(xssRes.dangerousEls1).toBe(0);
  expect(xssRes.hasHeading1).toBe(1);
  expect(xssRes.dangerousEls2).toBe(0);

  expect(xssRes.inLocalDefault.gemini).toBeNull();
  expect(xssRes.inLocalDefault.gh).toBeNull();
  expect(xssRes.inSessionDefault.gemini).toBe('AIza-secret-test');
  expect(xssRes.inSessionDefault.gh).toBe('ghp_secret_test');
  expect(xssRes.readBack.gemini).toBe('AIza-secret-test');
  expect(xssRes.readBack.gh).toBe('ghp_secret_test');
  expect(xssRes.inLocalOptIn).toBe('AIza-secret-test');
  expect(xssRes.inLocalAfterOff).toBeNull();
  expect(xssRes.sriCheck).toEqual({ marked: true, pdfjs: true, mammoth: true });
});

test('#3 Offline-Delete-Konflikt mit PostgREST-CAS (geänderte Remote-SHA löst Konflikt aus)', async ({ page }) => {
  const deleteCalls = [];
  const remoteState = { exists: true, sha256: 'sha-remote-newer-999' };

  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = req.url();
    if (url.startsWith('http://127.0.0.1:') || url.startsWith('http://localhost:')) {
      return route.continue();
    }
    if (url.startsWith('https://mock-remote.test/rest/v1/artefacts')) {
      if (req.method() === 'DELETE') {
        deleteCalls.push({ url, prefer: req.headers()['prefer'] || '' });
        // Simulate CAS mismatch (0 rows deleted because sha256 != sha-remote-newer-999)
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
      if (req.method() === 'GET') {
        if (url.includes('id=eq.art-1')) {
          const rows = remoteState.exists
            ? [{ id: 'art-1', stage: 'ssp', title: 'Test-SSP', filename: 'ssp.json', sha256: remoteState.sha256, updated_at: '2026-04-01T10:00:00Z', updated_by: 'other-user', data: { hello: 'new' } }]
            : [];
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(rows) });
        }
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
    }
    return route.abort();
  });

  await page.goto('/config.html');

  const res = await page.evaluate(async () => {
    gppCfg.set('db:url', 'https://mock-remote.test');
    // Minimal syntactically valid JWT payload with future exp
    const hdr = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const pay = btoa(JSON.stringify({ email: 'tester@example.org', org: 'ntt', gpp_role: 'editor', exp: Math.floor(Date.now() / 1000) + 3600 }));
    gppRemote._setSession({ access_token: `${hdr}.${pay}.sig`, expires_in: 3600 });

    // Queue offline delete with baseSha = 'sha-old-111'
    await gppRemote.onLocalRemove('art-1', 'sha-old-111', 'Test-SSP');
    await gppRemote.flush();
    const st1 = await gppRemote.status();
    const conflictEntries = (await gppRemote._outboxAll()).filter(e => e.conflict);
    return { st1, conflictEntries };
  });

  expect(deleteCalls.length).toBeGreaterThanOrEqual(1);
  expect(deleteCalls[0].url).toContain('id=eq.art-1');
  expect(deleteCalls[0].url).toContain('sha256=eq.sha-old-111');
  expect(deleteCalls[0].prefer).toContain('return=representation');

  // Conflict must be recorded instead of silently deleting!
  expect(res.st1.conflicts).toBe(1);
  expect(res.conflictEntries).toHaveLength(1);
  expect(res.conflictEntries[0].op).toBe('remove');
  expect(res.conflictEntries[0].id).toBe('art-1');
  expect(res.conflictEntries[0].baseSha).toBe('sha-old-111');
  expect(res.conflictEntries[0].conflict.op).toBe('remove');
  expect(res.conflictEntries[0].conflict.serverSha).toBe('sha-remote-newer-999');
});

test('#4 Stale Excel-Import mit Export-Baseline & Drei-Wege-Konfliktdialog', async ({ page }) => {
  await blockExternal(page);
  page.on('dialog', async (d) => { await d.accept(); });
  await page.goto('/ssp_ausfuellen.html');

  const compUuid = '11111111-1111-4111-8111-111111111111';
  const sspDoc = {
    'system-security-plan': {
      uuid: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      metadata: { title: 'Excel-3Way-SSP', version: '1.0', 'last-modified': '2026-01-01T00:00:00Z', 'oscal-version': '1.2.2' },
      'import-profile': { href: '#p1' },
      'system-characteristics': {
        'system-ids': [{ id: 's1' }],
        'system-name': 'Test',
        description: 'Test',
        'security-sensitivity-level': 'normal',
        'system-information': { 'information-types': [] },
        status: { state: 'operational' },
        'authorization-boundary': { description: 'Test' },
      },
      'system-implementation': {
        users: [],
        components: [{ uuid: compUuid, type: 'software', title: 'App-Server', description: 'App', status: { state: 'operational' } }],
      },
      'control-implementation': {
        description: 'Test',
        'set-parameters': [{ 'param-id': 'p-1', values: ['14 Tage (Baseline)'] }],
        'implemented-requirements': [
          {
            uuid: 'r1',
            'control-id': 'C-1',
            'by-components': [{ uuid: 'bc1', 'component-uuid': compUuid, description: 'Alt-C1', 'implementation-status': { state: 'partial' } }],
          },
          {
            uuid: 'r2',
            'control-id': 'C-2',
            'by-components': [{ uuid: 'bc2', 'component-uuid': compUuid, description: 'Alt-C2', 'implementation-status': { state: 'partial' } }],
          },
        ],
      },
    },
  };

  // Seed SSP in workspace set and reload so ssp_ausfuellen boots with the real SSP
  await page.evaluate(async (doc) => {
    await gppArtefacts.save({ stage: 'model', kind: 'ssp', title: 'Excel-3Way-SSP', filename: 'excel-ssp.json', tool: 'test', data: doc });
  }, sspDoc);
  await page.reload();
  await expect(page.locator('#ssp-editor')).toBeVisible();

  // 1. Export Excel (with _gpp_baseline), then advance SSP AFTER export
  const exportedBytesArr = await page.evaluate(async () => {
    const exportedBlob = exportControlsXlsx();
    return Array.from(new Uint8Array(await exportedBlob.arrayBuffer()));
  });

  // Update SSP in workspace set to simulate newer edits after export and reload
  const updatedSsp = JSON.parse(JSON.stringify(sspDoc));
  updatedSsp['system-security-plan']['control-implementation']['implemented-requirements'][0]['by-components'][0].description = 'Neuere SSP-Änderung C1';
  updatedSsp['system-security-plan']['control-implementation']['implemented-requirements'][1]['by-components'][0].description = 'SSP-Konflikt-Stand C2';
  updatedSsp['system-security-plan']['control-implementation']['set-parameters'][0].values = ['30 Tage (SSP)'];

  await page.evaluate(async (doc) => {
    await gppArtefacts.save({ stage: 'fill', kind: 'ssp', title: 'Excel-3Way-SSP', filename: 'excel-ssp.json', tool: 'test', data: doc });
  }, updatedSsp);
  await page.reload();
  await expect(page.locator('#ssp-editor')).toBeVisible();

  // 2. Modify the exported .xlsx in browser: change C-2 comment to 'Excel-Konflikt-Stand C2', leave C-1 & p-1 stale, keep _gpp_baseline intact!
  await page.evaluate(async (bytesArr) => {
    const bytes = new Uint8Array(bytesArr);
    const entries = await gppUnzip(new Blob([bytes]));
    const modified = entries.map(e => {
      if (e.name === 'xl/worksheets/sheet1.xml') {
        return { name: e.name, text: e.text.replace('Alt-C2', 'Excel-Konflikt-Stand C2') };
      }
      return { name: e.name, text: e.text };
    });
    const rebuilt = gppZip(modified);
    const file = new File([rebuilt], 'stale-edited.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    window.__importPromise = importControlsXlsx(file);
  }, exportedBytesArr);

  // 3. Conflict modal must appear ONLY for C-2!
  const modal = page.locator('#xls-conflict-modal');
  await expect(modal).toBeVisible();
  await expect(modal).toContainText('C-2');
  await expect(modal).not.toContainText('C-1');
  await expect(modal).not.toContainText('p-1');

  // Choose "Excel übernehmen" for C-2 and apply
  await modal.locator('input[name="xls-cf-0"][value="excel"]').check();
  await modal.locator('#xls-cf-apply').click();

  await page.evaluate(async () => { await window.__importPromise; });
  // Wait briefly for autoSave to persist to gppArtefacts
  const finalState = await page.evaluate(async () => {
    const rec = await gppArtefacts.latest('ssp');
    const ci = rec.data['system-security-plan']['control-implementation'];
    return {
      c1: ci['implemented-requirements'].find(r => r['control-id'] === 'C-1')['by-components'][0].description,
      c2: ci['implemented-requirements'].find(r => r['control-id'] === 'C-2')['by-components'][0].description,
      p1: ci['set-parameters'].find(p => p['param-id'] === 'p-1').values[0],
    };
  });

  expect(finalState.c1).toBe('Neuere SSP-Änderung C1');
  expect(finalState.p1).toBe('30 Tage (SSP)');
  expect(finalState.c2).toBe('Excel-Konflikt-Stand C2');
});

test('#8 Atomares Release-Manifest als Standard, Einzel-Overrides nur im Experten-Modus', async ({ page }) => {
  await blockExternal(page);
  await page.goto('/config.html');

  const check = await page.evaluate(() => {
    localStorage.clear();
    // Simulate a stray single override left in localStorage while expert mode is OFF
    localStorage.setItem('gpp:cfg:src:methodik-profil', 'https://example.invalid/custom.json');
    renderSources();

    const manifestId = gppReleaseManifest.active().id;
    const expertOff = gppReleaseManifest.expertOverridesEnabled();
    const urlWhenOff = gppSource('methodik-profil', 'https://fallback.invalid/m.json');
    const checkDisabled = document.getElementById('btn-check-all').disabled;

    // Enable expert mode -> override now applies and is recorded in backMatterProps
    gppReleaseManifest.setExpertOverrides(true);
    renderSources();
    const urlWhenOn = gppSource('methodik-profil', 'https://fallback.invalid/m.json');
    const propsWhenOn = gppReleaseManifest.backMatterProps();
    const checkEnabled = !document.getElementById('btn-check-all').disabled;

    return { manifestId, expertOff, urlWhenOff, checkDisabled, urlWhenOn, propsWhenOn, checkEnabled };
  });

  expect(check.manifestId).toBe('release-5.2');
  expect(check.expertOff).toBe(false);
  expect(check.checkDisabled).toBe(true);
  expect(check.urlWhenOff).not.toContain('example.invalid');
  expect(check.urlWhenOff).toContain('1880842a9bb07ce5d47cdda929aa31f713bc2cbf');
  expect(check.checkEnabled).toBe(true);
  expect(check.urlWhenOn).toBe('https://example.invalid/custom.json');
  expect(check.propsWhenOn.some(p => p.name === 'expert-source-overrides' && p.value === 'methodik-profil')).toBe(true);
});

test('#9 Viewer NG-Check: fehlender oder hash-abweichender NG-Import wird NICHT grün gemeldet', async ({ page }) => {
  const baseCatalogObj = {
    catalog: {
      uuid: 'cat-base-1',
      metadata: { title: 'Basis-Katalog', version: '1.0', 'last-modified': '2026-01-01T00:00:00Z', 'oscal-version': '1.2.2' },
      groups: [{ id: 'G1', title: 'Gruppe 1', controls: [{ id: 'BASE-1', title: 'Basis Control 1' }] }],
    },
  };
  const baseCatalogText = JSON.stringify(baseCatalogObj);
  const baseHash = sha256(baseCatalogText);

  const ngCatalogObj = {
    catalog: {
      uuid: 'cat-ng-1',
      metadata: { title: 'NG-Ergänzungskatalog', version: '1.0', 'last-modified': '2026-01-01T00:00:00Z', 'oscal-version': '1.2.2' },
      groups: [{ id: 'NG', title: 'NG', controls: [{ id: 'NG-1', title: 'NG Control 1' }] }],
    },
  };
  const ngCatalogText = JSON.stringify(ngCatalogObj);
  const ngValidHash = sha256(ngCatalogText);
  const ngWrongHash = '0'.repeat(64);

  const makeProfile = (ngHref, ngHash) => JSON.stringify({
    profile: {
      uuid: 'prof-test',
      metadata: { title: 'NG-Test-Profil', version: '1.0', 'last-modified': '2026-01-01T00:00:00Z', 'oscal-version': '1.2.2' },
      imports: [
        { href: '#res-base', 'include-controls': [{ 'with-ids': ['BASE-1'] }] },
        { href: '#res-ng', 'include-controls': [{ 'with-ids': ['NG-1'] }] },
      ],
      'back-matter': {
        resources: [
          { uuid: 'res-base', rlinks: [{ href: 'https://mock-viewer.test/base.json', hashes: [{ algorithm: 'SHA-256', value: baseHash }] }] },
          { uuid: 'res-ng', rlinks: [{ href: ngHref, hashes: [{ algorithm: 'SHA-256', value: ngHash }] }] },
        ],
      },
    },
  });

  await page.route('**/*', (route) => {
    const url = route.request().url();
    if (url.startsWith('http://127.0.0.1:') || url.startsWith('http://localhost:')) return route.continue();
    if (url === 'https://mock-viewer.test/base.json') return route.fulfill({ status: 200, contentType: 'application/json', body: baseCatalogText });
    if (url === 'https://mock-viewer.test/ng-valid.json') return route.fulfill({ status: 200, contentType: 'application/json', body: ngCatalogText });
    if (url === 'https://mock-viewer.test/ng-missing.json') return route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' });
    if (url === 'https://mock-viewer.test/prof-badhash.json') return route.fulfill({ status: 200, contentType: 'application/json', body: makeProfile('https://mock-viewer.test/ng-valid.json', ngWrongHash) });
    if (url === 'https://mock-viewer.test/prof-missing.json') return route.fulfill({ status: 200, contentType: 'application/json', body: makeProfile('https://mock-viewer.test/ng-missing.json', ngValidHash) });
    if (url === 'https://mock-viewer.test/prof-valid.json') return route.fulfill({ status: 200, contentType: 'application/json', body: makeProfile('https://mock-viewer.test/ng-valid.json', ngValidHash) });
    return route.abort();
  });

  await page.goto('/GSpp-Viewer.html');

  // Load base catalog first
  await page.evaluate(async () => {
    document.getElementById('urlInput').value = 'https://mock-viewer.test/base.json';
    await loadFromURL();
  });

  const runProfile = async (profileUrl) => page.evaluate(async (u) => {
    const sel = document.getElementById('profileSelect');
    const opt = document.createElement('option');
    opt.value = u;
    opt.textContent = u;
    sel.appendChild(opt);
    sel.value = u;
    await handleProfileChange();
    const info = document.getElementById('profileInfo');
    return { text: info.textContent, color: info.style.color };
  }, profileUrl);

  // Case A: Hash-mismatched NG import -> RED error, NOT green, NG unresolved
  const badHash = await runProfile('https://mock-viewer.test/prof-badhash.json');
  expect(badHash.color).toBe('var(--red)');
  expect(badHash.text).toContain('SHA-256-Abweichung');
  expect(badHash.text).toContain('1 NG unaufgelöst');

  // Case B: Missing (404) NG import -> RED error, NOT green, NG unresolved
  const missingNg = await runProfile('https://mock-viewer.test/prof-missing.json');
  expect(missingNg.color).toBe('var(--red)');
  expect(missingNg.text).toContain('FEHLER');
  expect(missingNg.text).toContain('1 NG unaufgelöst');

  // Case C: Valid SHA-256 matching NG import -> GREEN, verified
  const validNg = await runProfile('https://mock-viewer.test/prof-valid.json');
  expect(validNg.color).toBe('var(--green)');
  expect(validNg.text).toContain('NG-Import SHA-256 geprüft');
});
