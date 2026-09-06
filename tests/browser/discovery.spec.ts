import { test, expect, type Page } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`search detail compare and verify at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 960});
    const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/?source=candidates&q=rtk.shell_output_proxy');
    await expect(page.locator('#detail h2')).toHaveText('RTK Shell Output Compression Proxy');
    await page.evaluate(()=>document.fonts.ready);
    expect(await page.evaluate(()=>document.fonts.check('24px "Instrument Serif"'))).toBeTruthy();
    expect(await page.locator('h1').evaluate(e=>getComputedStyle(e).fontFamily)).toContain('Instrument Serif');
    expect(await page.locator('#search').evaluate(e=>getComputedStyle(e).borderRadius)).toBe('0px');
    const bounds=await page.evaluate(()=>{
      const rect=(selector:string)=>{const r=document.querySelector(selector)!.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};};
      return {brand:rect('.brand'),status:rect('#status'),list:rect('aside'),detail:rect('article')};
    });
    expect(bounds.brand.right).toBeLessThanOrEqual(bounds.status.x);
    if(width>760) expect(bounds.list.right).toBeLessThanOrEqual(bounds.detail.x);
    else expect(bounds.list.bottom).toBeLessThanOrEqual(bounds.detail.y);
    await page.getByRole('button',{name:'Verify metadata'}).click();
    await expect(page.locator('.verification')).toHaveText('matched_metadata');
    await page.locator('.snippet a').first().click();
    await expect(page.getByRole('dialog',{name:'Source field'})).toBeVisible();
    await page.getByRole('button',{name:'Close source field'}).click();
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await expect.poll(()=>page.locator('img').evaluateAll(images=>images.every(i=>(i as HTMLImageElement).naturalWidth>0))).toBeTruthy();
    await page.screenshot({path:`.data/screenshots/shared-design-detail-${width}.png`,fullPage:false});
    await page.locator('#query').fill('HTTP');await page.locator('#mode').selectOption('lexical');
    await page.getByRole('button',{name:'Search',exact:true}).click();
    await expect(page.locator('#results .result')).not.toHaveCount(0);
    const checks=page.locator('#results input[type=checkbox]');
    await checks.nth(0).check();await expect(page.locator('#compare')).toHaveText('Compare (1)');
    await checks.nth(1).check();await expect(page.locator('#compare')).toHaveText('Compare (2)');
    await page.locator('#compare').click();await expect(page.locator('#comparison')).toBeVisible();
    await page.screenshot({path:`.data/screenshots/shared-design-compare-${width}.png`,fullPage:false});
    await page.getByRole('button',{name:'Close comparison'}).click();
    expect(errors).toEqual([]);
  });
}

test('hostile package text stays inert',async({page})=>{
  await page.route('**/v1/packages/**',async route=>{
    const response=await route.fetch();const body=await response.json();
    body.summary='<img src=x onerror="window.pwned=true">';
    await route.fulfill({json:body});
  });
  await page.goto('/?source=candidates&q=rtk.shell_output_proxy');
  await expect(page.locator('.detail-summary')).toContainText('<img');
  expect(await page.evaluate(()=>('pwned' in window))).toBeFalsy();
  await expect(page.locator('.detail-summary img')).toHaveCount(0);
});

for(const width of [1440,390]) {
  test(`compact capability fields at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:960});
    await page.route('**/v1/packages/**',async route=>{
      const response=await route.fetch();const body=await response.json();
      body.details.specs=[{provides:{capabilities:[{id:'openai.codex.local_agent_turns',role:'primary',summary:'Run a local coding-agent turn from the Codex CLI against a repository-oriented working context and receive the agent result through the CLI surface.'}]}}];
      await route.fulfill({json:body});
    });
    await page.goto('/?source=candidates&q=rtk.shell_output_proxy');
    const section=page.locator('#detail .section').filter({has:page.getByRole('heading',{name:'Capabilities',exact:true})});
    await expect(section.locator('dt')).toHaveText(['id','role','summary']);
    const role=section.locator('.field-row').filter({has:page.locator('dt').filter({hasText:/^role$/})});
    const bounds=await role.evaluate(e=>{const label=e.querySelector('dt')!.getBoundingClientRect();const value=e.querySelector('dd')!.getBoundingClientRect();return {height:e.getBoundingClientRect().height,labelY:label.y,valueY:value.y,labelRight:label.right,valueX:value.x};});
    expect(bounds.height).toBeLessThan(32);
    expect(bounds.labelY).toBe(bounds.valueY);
    expect(bounds.labelRight).toBeLessThan(bounds.valueX);
    expect((await section.boundingBox())!.height).toBeLessThan(width>760?220:320);
    await section.scrollIntoViewIfNeeded();
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:`.data/screenshots/compact-capabilities-${width}.png`});
  });
}

function deferred(){let resolve!:()=>void;const promise=new Promise<void>(done=>{resolve=done;});return {promise,resolve};}
async function mockComparison(page:Page){
  const packages=['a','b','c','d'].map(id=>({
    record_id:id,package_id:`fixture.${id}`,version:'1.0.0',name:`Package ${id}`,summary:`Summary ${id}`,
    source_kind:'registry',source_id:'fixture',license:'MIT',digest:`digest-${id}`,
    details:{metadata:{provided_intents:[`intent.${id}`],provided_capabilities:[`capability.${id}`],required_capabilities:id==='c'?[]:[`dependency.${id}`]}} as Record<string,unknown>,
    evidence:[],provenance:{},documents:[],
  }));
  packages[1].source_kind='candidates';
  packages[1].details={metadata:{provided_capabilities:['wrong.metadata']},specs:[{
    intent:'Candidate intent',provides:{capabilities:[{id:'candidate.run',role:'primary'}]},requires:['candidate.dependency'],
  }]};
  type Hold={arrived:ReturnType<typeof deferred>;gate:ReturnType<typeof deferred>;status:number;name?:string};
  const holds=new Map<string,Hold[]>();
  let searches=0;
  await page.route('**/v1/status',route=>route.fulfill({json:{packages:4}}));
  await page.route('**/v1/search',route=>route.fulfill({json:{
    snapshot:`snapshot-${++searches}`,mode:'lexical',latency_ms:1,degraded:false,
    results:packages.map(p=>({...p,source:p.source_kind,metadata_only:p.source_kind==='registry',match_strength:'exact',ranking_score:null,snippets:[]})),
  }}));
  await page.route('**/v1/packages/**',async route=>{
    const id=decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop()!);
    const p=packages.find(p=>p.record_id===id)!;
    const hold=holds.get(id)?.shift();
    if(hold){hold.arrived.resolve();await hold.gate.promise;}
    await route.fulfill({status:hold?.status??200,json:hold&&hold.status!==200?{detail:'Delayed package failure'}:{...p,name:hold?.name??p.name}});
  });
  await page.goto('/?q=fixture&source=all');
  await expect(page.locator('#detail h2')).toHaveText('Package a');
  await expect(page.locator('#search')).toBeEnabled();
  return {
    check:(id:string)=>page.getByRole('checkbox',{name:`Compare fixture.${id}`,exact:true}),
    hold:(id:string,status=200,name?:string)=>{
      const hold:Hold={arrived:deferred(),gate:deferred(),status,name};
      holds.set(id,[...(holds.get(id)||[]),hold]);
      return {arrived:hold.arrived.promise,release:async()=>{
        const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/v1/packages/${id}`);
        hold.gate.resolve();await (await response).finished();
        // Let the fetch continuation render before asserting that stale responses had no effect.
        await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
      }};
    },
  };
}

test('pending comparisons reserve three slots and survive result rerenders',async({page})=>{
  const mock=await mockComparison(page);
  const pending=['a','b','c'].map(id=>mock.hold(id));
  for(const id of ['a','b','c'])await mock.check(id).check();
  await Promise.all(pending.map(p=>p.arrived));
  await expect(page.locator('#compare')).toHaveText('Compare (3)');
  await expect(page.locator('#compare')).toBeDisabled();
  // The fourth checkbox is synchronously rejected, so use click rather than check.
  await mock.check('d').click();
  await expect(mock.check('d')).not.toBeChecked();
  await expect(page.locator('#notice')).toHaveText('Comparison limit: 3 packages');
  await page.locator('.result[data-id="d"] .result-open').click();
  await expect(page.locator('#detail h2')).toHaveText('Package d');
  for(const id of ['a','b','c'])await expect(mock.check(id)).toBeChecked();
  await pending[2].release();await pending[1].release();
  await expect(page.locator('#compare')).toBeDisabled();
  await pending[0].release();
  await expect(page.locator('#compare')).toBeEnabled();
  await page.locator('#compare').click();
  await expect(page.locator('#comparison tr').first().locator('th')).toHaveText(['','Package a','Package b','Package c']);
});

for(const status of [200,500]){
  test(`unchecking invalidates a pending ${status} response`,async({page})=>{
    const mock=await mockComparison(page);const old=mock.hold('b',status);
    await mock.check('b').check();await old.arrived;
    // The original checkbox is detached by this detail navigation.
    await page.locator('.result[data-id="d"] .result-open').click();
    await expect(page.locator('#detail h2')).toHaveText('Package d');
    await mock.check('b').uncheck();
    const notice=await page.locator('#notice').textContent();
    await old.release();
    await expect(mock.check('b')).not.toBeChecked();
    await expect(page.locator('#compare')).toHaveText('Compare (0)');
    await expect(page.locator('#compare')).toBeDisabled();
    await expect(page.locator('#notice')).toHaveText(notice!);
  });

  test(`reselection is not overwritten by an older ${status} response`,async({page})=>{
    const mock=await mockComparison(page);const old=mock.hold('b',status,'Stale package');
    await mock.check('b').check();await old.arrived;await mock.check('b').uncheck();
    const fresh=mock.hold('b',200,'Fresh package');
    await mock.check('b').check();await fresh.arrived;
    await fresh.release();await mock.check('a').check();
    await expect(page.locator('#compare')).toBeEnabled();
    const notice=await page.locator('#notice').textContent();
    await old.release();
    await expect(mock.check('b')).toBeChecked();
    await expect(page.locator('#compare')).toHaveText('Compare (2)');
    await expect(page.locator('#notice')).toHaveText(notice!);
    await page.locator('#compare').click();
    await expect(page.locator('#comparison tr').first().locator('th')).toHaveText(['','Fresh package','Package a']);
  });

  test(`a new search invalidates a pending ${status} comparison`,async({page})=>{
    const mock=await mockComparison(page);const old=mock.hold('b',status,'Old snapshot package');
    await mock.check('b').check();await old.arrived;
    const gate=deferred();const arrived=deferred();
    await page.route('**/v1/search',async route=>{arrived.resolve();await gate.promise;await route.fallback();});
    await page.locator('#query').fill('next search');await page.locator('#search').click();await arrived.promise;
    await expect(page.locator('#results input')).toHaveCount(0);
    await expect(page.locator('#compare')).toHaveText('Compare (0)');
    await old.release();
    await expect(page.locator('#compare')).toHaveText('Compare (0)');
    await expect(page.locator('#notice')).toHaveText('Searching');
    gate.resolve();await expect(page.locator('#search')).toBeEnabled();
    await expect(mock.check('b')).not.toBeChecked();
    await mock.check('b').check();await mock.check('a').check();
    await expect(page.locator('#compare')).toBeEnabled();await page.locator('#compare').click();
    await expect(page.locator('#comparison tr').first().locator('th')).toHaveText(['','Package b','Package a']);
  });
}

test('a failed active comparison frees its reserved slot after a rerender',async({page})=>{
  const mock=await mockComparison(page);const failed=mock.hold('b',500);
  await mock.check('b').check();await failed.arrived;
  await mock.check('a').check();await mock.check('c').check();
  await page.locator('.result[data-id="d"] .result-open').click();
  await expect(page.locator('#detail h2')).toHaveText('Package d');
  await failed.release();
  await expect(mock.check('b')).not.toBeChecked();
  await expect(page.locator('#notice')).toContainText('Delayed package failure');
  await expect(page.locator('#compare')).toHaveText('Compare (2)');
  await mock.check('d').check();await expect(page.locator('#compare')).toHaveText('Compare (3)');
  await expect(page.locator('#compare')).toBeEnabled();
});

for(const width of [1440,390]){
  test(`comparison maps registry metadata and preserves compact candidate fields at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:960});
    const mock=await mockComparison(page);
    for(const id of ['a','b','c'])await mock.check(id).check();
    await expect(page.locator('#compare')).toBeEnabled();await page.locator('#compare').click();
    const row=(key:string)=>page.locator('#comparison tr').filter({has:page.locator('th').filter({hasText:new RegExp(`^${key}$`)})});
    await expect(row('intent').locator('td')).toHaveText(['intent.a','Candidate intent','intent.c']);
    await expect(row('provides').locator('td').nth(0)).toHaveText('capability.a');
    await expect(row('provides').locator('td').nth(2)).toHaveText('capability.c');
    await expect(row('requires').locator('td')).toHaveText(['dependency.a','candidate.dependency','No entries declared']);
    await expect(row('interfaces').locator('td').first()).toHaveText('Not declared');
    const candidate=row('provides').locator('td').nth(1);
    await expect(candidate.locator('dt')).toHaveText(['capabilities','id','role']);
    await expect(candidate).toContainText('candidate.run');await expect(candidate).not.toContainText('wrong.metadata');
    await expect(page.locator('#comparison pre')).toHaveCount(0);
    const role=candidate.locator('.field-row').filter({has:page.locator('dt').filter({hasText:/^role$/})}).last();
    const bounds=await role.evaluate(e=>{const label=e.querySelector('dt')!.getBoundingClientRect();const value=e.querySelector('dd')!.getBoundingClientRect();return {height:e.getBoundingClientRect().height,labelY:label.y,valueY:value.y,labelRight:label.right,valueX:value.x};});
    if(width>760){expect(bounds.height).toBeLessThan(32);expect(bounds.labelY).toBe(bounds.valueY);expect(bounds.labelRight).toBeLessThan(bounds.valueX);}
    else {expect(bounds.height).toBeLessThan(64);expect(bounds.valueY).toBeGreaterThan(bounds.labelY);}
  });
}
