import { test, expect } from '@playwright/test';

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
