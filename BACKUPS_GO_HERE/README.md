# BACKUP FOLDER - ALL BACKUPS GO HERE

## Structure

```
BACKUPS_GO_HERE/
├── csv_backups/      <- CSV file backups (portfolio_data_backup_*.csv)
├── script_backups/   <- Python script backups (*_backup_*.py)
└── legacy_archive/   <- Old archived files
```

## Rules for Claude

1. **CSV Backups**: When creating backups of `portfolio_data.csv` or any other CSV, save them to:
   ```
   BACKUPS_GO_HERE/csv_backups/
   ```

2. **Script Backups**: When creating backups of Python scripts, save them to:
   ```
   BACKUPS_GO_HERE/script_backups/
   ```

3. **NEVER** create backup files in:
   - `data/source/` (only live data files go here)
   - `scripts/` (only active scripts go here)
   - `src/` (only active source code goes here)
   - Root directory

4. Backup naming convention:
   - CSVs: `{original_name}_backup_{YYYYMMDD_HHMMSS}.csv`
   - Scripts: `{original_name}_backup_{YYYYMMDD_HHMMSS}.py`
