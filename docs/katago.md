# KataGo Scoring

Official-style local scoring uses KataGo analysis mode with fixed settings:

```bash
export GOBENCH_SCORER=katago
export KATAGO_BIN=/opt/homebrew/bin/katago
export KATAGO_MODEL=/opt/homebrew/Cellar/katago/1.16.4/share/katago/g170-b40c256x2-s5095420928-d1229425124.bin.gz
export KATAGO_CONFIG=configs/katago_gobench_official.cfg
export KATAGO_MAX_VISITS=2048
export KATAGO_ANALYSIS_PV_LEN=12
export KATAGO_REPORT_ANALYSIS_AS=SIDETOMOVE
```

The official config disables neural-net randomization and wide-root noise.
Record the KataGo binary version, model filename or digest, config digest, and
visit count for any reported benchmark result.
