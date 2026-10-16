# Automatic native EndNote attachment workflow

**Legacy opt-in only (v2.0):** The default workflow generates Markdown for manual attachment. Do not launch EndNote, export XML, back up a library, or run these helpers during ordinary summary generation. This reference applies only after the user explicitly requests automatic attachment again.

Tested on Windows EndNote 22.3.1 (Chinese UI), 2026-10-06. A live summary was attached to an existing reference and opened via MarkText. Native app access must be available; a browser-only controller is insufficient. Read the available computer-use skill and its API/confirmation guidance before operating EndNote. Use its supported native controller (currently `@oai/sky` in the Node REPL), never injected GUI automation or direct database edits.

## Observe and export

1. Observe installed/running EndNote and select its actual returned window. If needed, launch the installed app through the native controller. Identify the active `.enl` path from observed library information and read-only filesystem inspection. With multiple possible libraries, ask for the intended library. Never assume a remembered record number belongs to the current library.
2. On first writeback to a library in this run, use File → Compressed Library (`压缩个人图书馆 (.enlx)`) → Create, Include File Attachments, All References → Next, and save a new `.enlx` in the writable output directory. Avoid overwriting an existing backup. Check completion before further actions.
3. Select All References (`所有参考文献`) and clear active searches (`清除检索`) so the displayed count is the complete library count. Open File → Export (`导出`) or the observed export toolbar button. In the export dialog choose **XML (*.xml)** as Save as type, uncheck Export Selected References (`导出选定的参考文献`), and save a new `before.xml`. The output style can remain Annotated; setting it to a style named XML is unnecessary. Inspect the file and check exported count against the visible total. Save-as format and the selection checkbox reset on each export in the tested version.

## Plan and attach

4. Prepare bibliographic matching against `before.xml`, package the summary, then run `endnote_writeback.py plan`. It validates source and summary hashes, library paths recorded in the export, and a unique strong match. Read the printed target record number/title/DOI and action. A helper's plan does not itself register an attachment. The tested EndNote 22.3 XML export omitted the Markdown attachment entirely. Always inspect the native target's complete attachment list before adding, even when plan initially says `attach_file`. If existing non-PDF attachments are present, record a fresh native observation as below and rerun plan with `--native-observation native-before.json`; this allows byte-identical Markdown detection and preserves earlier versions. Never conclude that an attachment is absent merely from the XML snapshot.
5. For `skip_existing`, do not add another attachment. For `attach_file`, search the title or DOI in EndNote using the observed search fields. Inspect the current result, native reference number shown with `#`, title, DOI, and existing PDF. All must agree with the plan. Multiple matches or conflicting evidence require clarification; keep the completed summary.
6. Click the target's Attach File (`附加文件`). Select the exact summary path and verify the checkbox `将此文件复制到默认的文件附件文件夹并创建相对链接` is selected. Click Open. Re-observe the same reference with the original PDF plus the new Markdown. Preserve all previous attachments and notes. A changed summary may be appended as a new version; do not automatically remove earlier versions.

## Verify and report

7. Open the summary from the EndNote attachment menu: Open / `使用'marktext'打开` was observed in this installation. Inspect the associated app's actual file path and visible content. The opened path should be the registered EndNote copy, not merely the workspace source. Do not type into the copied summary. If no associated app is available, verify the readable bytes but accurately report visual open verification incomplete.
8. Switch to another reference and back to the target, verifying the registered attachments persist. Record a fresh `native-after.json`. Clear search, restore All References, export `after.xml` with XML Save as type and Export Selected References unchecked again. Run `endnote_writeback.py verify --native-observation native-after.json`, providing `--opened-attachment` and `--opened-app` only after observing them. It checks unchanged record IDs/count and exported metadata, preserved observed attachments, no other reference changed exported attachments, and exactly one byte-identical Markdown copy on the target. Native observations supplement non-PDF registration because XML omitted it in the tested version. A failing verification is not success; investigate and retain backup/evidence without speculative repair.
9. For repeat invocation with unchanged output, create a new complete snapshot and run plan. `skip_existing` prevents duplicate attachments. Verify that snapshot again and record the skipped action. Do not change the Markdown bytes after attaching just to update its status: the sidecar is the authoritative live audit.

## Native controller reliability

The agent creates native observation JSON only from actual fresh UI inspection. It includes the active library path, the native reference number, exact title/DOI, ISO observation time, `reference_reopened: true`, and the complete observed attachment list. For each attachment, use its displayed filename and actual copied path established by opening it in the associated app, or resolving an exported URI for that same displayed filename. Do not fabricate paths or treat arbitrary files found under `.Data` as registered. Example schema (all placeholders must be observed):

```json
{
  "library_path": "ACTUAL-LIBRARY.enl",
  "record_number": "OBSERVED-NUMBER",
  "title": "OBSERVED-TITLE",
  "doi": "OBSERVED-DOI-OR-EMPTY",
  "observed_at": "ACTUAL-ISO-TIME",
  "reference_reopened": true,
  "attachments": [
    {"displayed_filename": "OBSERVED-FILENAME", "path": "ACTUAL-COPIED-PATH"}
  ]
}
```

The helper validates identity, filenames, local library containment and file bytes, but cannot independently prove the agent actually observed the UI. The agent must inspect it and truthfully record the evidence. Without current native evidence, a file copied on disk alone is insufficient.

Observe → act → immediately observe in separate reasoning steps, with the actual returned Window. Never reuse indexes, screenshots or guessed coordinates across different states. In the tested UI toolbar/menu indexes sometimes expired before the next call; after one failed indexed action, refresh and use a coordinate grounded in the latest screenshot. The computer-use docs require fresh state after each action. Some custom dialogs are absent from the accessibility tree but visible in the bounded screenshot. Translation popovers may obscure controls: target a visible unobscured control or dismiss/refresh; do not disable unrelated applications.

## Scope

Calling the skill in a local Codex chat with native app access performs this workflow on demand. It is not an EndNote plugin, automatic filesystem watcher, or service running after the chat ends. In cloud/browser-only environments deliver summary/matching artifacts and report writeback unavailable. Invoking the installed skill alone cannot grant unavailable desktop permissions.
