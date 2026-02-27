# Notion Database Schema Reference

## Required Properties

| Property Name | Type | Notes |
|---|---|---|
| `Name` (configurable) | `title` | Page title / journal entry name |
| `Formulated Date` (configurable) | `date` | Date of the journal entry |

## Optional / Auto-detected Properties

| Property Name | Type | Notes |
|---|---|---|
| `created_time` | built-in | Fallback date if `Formulated Date` not set |

## Properties Added by Writeback (writeback_notion.py)

| Property Name | Type | Notes |
|---|---|---|
| `ClusterId` | `number` | Cluster assignment (-1 = noise) |
| `LoopLabel` | `rich_text` | Human-readable cluster label |
| `IsDuplicate` | `checkbox` | True if page contains duplicate chunks |
| `CanonicalPage` | `url` | Link to canonical page (if duplicate) |
| `CanonicalChunk` | `rich_text` | Canonical chunk ID |

## How to Set Up

1. Create a Notion integration at https://www.notion.so/my-integrations
2. Copy the **Internal Integration Token** → set as `NOTION_TOKEN` in `.env`
3. Open your Journal database in Notion
4. Click `...` → `Add connections` → select your integration
5. Copy the database URL: `https://www.notion.so/YOUR_WORKSPACE/DATABASE_ID?v=...`
   - The `DATABASE_ID` is the 32-char hex string before `?v=`
   - Set as `NOTION_DATABASE_ID` in `.env`

## Date Property Notes

- If your date property is named differently (e.g., `Date`, `Created`, `日期`),
  update `NOTION_DATE_PROPERTY` in `.env`
- If no date property exists, the pipeline uses `created_time` automatically
- All dates are normalized to `YYYY-MM-DD` format internally

## Block Types Supported

The `blocks_to_text.py` converter handles:
- `paragraph`, `heading_1/2/3`
- `bulleted_list_item`, `numbered_list_item`
- `to_do`, `toggle`, `quote`, `callout`
- `code`, `divider`, `equation`
- `image`, `video`, `file`, `bookmark`
- `table_row`, `child_page`
- Nested children (recursive)
