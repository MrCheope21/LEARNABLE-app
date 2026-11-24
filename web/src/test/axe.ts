import axe from "axe-core";

/** Structural accessibility checks (names, roles, labels, landmarks) with axe. Colour contrast
 * needs a real browser and is left out here. */
export async function violations(container: HTMLElement): Promise<string[]> {
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 90)).join(" | ")}`);
}
