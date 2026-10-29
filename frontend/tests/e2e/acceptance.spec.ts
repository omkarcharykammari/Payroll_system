import { test, expect } from '@playwright/test';

test.describe('Prompt Pack Acceptance Tests (Scenarios 1 to 8)', () => {

  test('Scenario 1: Authentication & Navigation — landing and login form render', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveTitle(/Vertex|Login/i);
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"], input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('Scenario 2: Company Sign-up & Onboarding Form', async ({ page }) => {
    await page.goto('/signup');
    await expect(page.locator('text=Create your organization account').or(page.locator('text=Sign up')).or(page.locator('input[name="company_name"]'))).toBeVisible();
  });

  test('Scenario 3: Employee Invitation & Accept Invite page', async ({ page }) => {
    await page.goto('/accept-invite?token=test-token-preview');
    await expect(page.locator('text=Set Your Password').or(page.locator('input[name="password"]'))).toBeVisible();
  });

  test('Scenario 4: Password Reset Flow Form', async ({ page }) => {
    await page.goto('/forgot-password');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('Scenario 5: Admin Login and Dashboard View', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@example.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    // Upon login redirect to dashboard
    await page.waitForURL('**/dashboard', { timeout: 10000 });
    await expect(page.locator('text=Payroll').or(page.locator('text=Dashboard'))).toBeVisible();
  });

  test('Scenario 6: Employee Directory & Search Navigation', async ({ page }) => {
    // Navigate with storage/cookie from previous step or direct page check
    await page.goto('/employees');
    await expect(page.locator('text=Employees').or(page.locator('table')).or(page.locator('input[placeholder*="Search"]'))).toBeVisible();
  });

  test('Scenario 7: Attendance & Regularisation Tab UI', async ({ page }) => {
    await page.goto('/attendance');
    await expect(page.locator('text=Attendance').or(page.locator('table'))).toBeVisible();
  });

  test('Scenario 8: Payroll Run & Payslips Download Hub', async ({ page }) => {
    await page.goto('/payslips');
    await expect(page.locator('text=Payslips').or(page.locator('table'))).toBeVisible();
  });
});
