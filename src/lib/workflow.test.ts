import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const temp = fs.mkdtempSync(path.join(os.tmpdir(), "signgate-"));
const prevCwd = process.cwd();

describe("workflow gate", () => {
  afterEach(() => {
    process.chdir(prevCwd);
  });

  it("opens on generate and blocks on the adversarial edit", async () => {
    process.chdir(temp);
    const workflow = await import("./workflow");
    const created = workflow.createDocument(
      "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal.",
    );
    const id = created.document.id;
    workflow.approveManifest(id, "human:judge");
    const opened = await workflow.generateDocument(id, "human:judge");
    expect(opened.decision?.status).toBe("open");
    expect(opened.decision?.critical_count).toBe(0);

    const blocked = await workflow.introduceAdversary(id, "human:judge");
    expect(blocked.decision?.status).toBe("blocked");
    const fields = blocked.decision?.discrepancies.map((item) => item.field) ?? [];
    expect(fields).toEqual(expect.arrayContaining(["contract_value", "auto_renewal", "attachments"]));

    await expect(workflow.requestSignature(id, "human:judge")).rejects.toThrow(/BLOCKED/);

    const restored = await workflow.restoreApproved(id, "human:judge");
    expect(restored.decision?.status).toBe("open");
    const handed = await workflow.requestSignature(id, "human:judge");
    expect(handed.signature_request?.status).toBe("prepared");
    expect(handed.document.status).toBe("sent_for_signature");
  });
});
