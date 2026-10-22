// Chapter "integrations": the catalogue, the VoiceStudio API page with its
// setup snippets, MCP voice bindings and the API reference.
export default async function capture({ page, goto, shot, t, L }) {
  const card = (name) =>
    page.locator('button.integration-card', { has: page.getByRole('heading', { name, exact: true }) });

  await goto('/integrations');
  await page.locator('button.integration-card').first().waitFor({ timeout: 30000 });
  await page.locator('.integrations-search input').fill('VoiceStudio API');
  await shot('integrations-catalog', {
    marks: [page.locator('.integrations-search'), page.locator('.integrations-filters'), card('VoiceStudio API')],
  });

  await card('VoiceStudio API').click();
  await page.waitForURL(/integrations\/voicestudio-api/);
  const hero = page.locator('.integration-detail-hero');
  await hero.waitFor({ timeout: 30000 });
  const setup = page.locator('section[aria-labelledby="integration-setup-title"]');
  const baseUrl = setup.locator('.integration-setup-block').first();
  await baseUrl.waitFor({ timeout: 30000 });
  await setup.locator('h3#integration-setup-title').scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -120);
  await shot('integrations-api', {
    marks: [hero.getByRole('heading').first(), hero.getByText(L('common.learn_more')),
      setup.locator('h3#integration-setup-title'), baseUrl],
  });

  await goto('/settings/sharing');
  const bindings = page.getByRole('heading', { name: L('settings.mcp_title') });
  await bindings.waitFor({ timeout: 30000 });
  await bindings.scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 400);
  await shot('integrations-mcp', {
    marks: [
      page.getByRole('textbox', { name: L('settings.mcp_client_id'), exact: true }),
      page.getByRole('combobox', { name: L('settings.mcp_voice_profile') }),
      page.getByRole('button', { name: L('settings.mcp_add_title') }),
    ],
  });

  await goto('/settings/openapi');
  // Scalar renders the spec into its own <main>, relabelled as this region.
  await page.getByRole('region', { name: L('openapi.title') })
    .first().waitFor({ timeout: 180000 });
  await page.waitForTimeout(3000);
  await shot('integrations-openapi', {
    marks: [
      page.getByRole('button', { name: L('openapi.copy_url') }),
      page.getByText('OpenAI-Compatible Audio API', { exact: true }).first(),
    ],
  });
}
