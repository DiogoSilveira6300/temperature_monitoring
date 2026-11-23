#!/bin/bash
# Wazuh - Yara active response
# Copyright (C) 2015-2022, Wazuh Inc.
#
# This program is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public
# License (version 2) as published by the FSF - Free Software
# Foundation.


#------------------------- Gather parameters -------------------------#

# Extra arguments
read INPUT_JSON
YARA_PATH=$(echo $INPUT_JSON | jq -r .parameters.extra_args[1])
YARA_RULES=$(echo $INPUT_JSON | jq -r .parameters.extra_args[3])
FILENAME=$(echo $INPUT_JSON | jq -r .parameters.alert.syscheck.path)

# Set LOG_FILE path
LOG_FILE="logs/active-responses.log"

size=0
actual_size=$(stat -c %s ${FILENAME})
while [ ${size} -ne ${actual_size} ]; do
    sleep 1
    size=${actual_size}
    actual_size=$(stat -c %s ${FILENAME})
done

#----------------------- Analyze parameters -----------------------#

if [[ ! $YARA_PATH ]] || [[ ! $YARA_RULES ]]
then
    echo "wazuh-yara: ERROR - Yara active response error. Yara path and rules parameters are mandatory." >> ${LOG_FILE}
    exit 1
fi

#------------------------- Main workflow --------------------------#

if ! yara_output="$("${YARA_PATH}/yara" -w -r "$YARA_RULES" "$FILENAME" 2>> "$LOG_FILE")"; then
    echo "wazuh-yara: ERROR - Scan failed: $FILENAME" >> "$LOG_FILE"
    exit 1
fi

if [[ -n "$yara_output" ]]; then
    while IFS= read -r line; do
        echo "wazuh-yara: INFO - Scan result: $line" >> "$LOG_FILE"
    done <<< "$yara_output"

    if [[ -f "$FILENAME" && ! -L "$FILENAME" ]]; then
        if rm -- "$FILENAME"; then
            echo "wazuh-yara: INFO - Deleted: $FILENAME" >> "$LOG_FILE"
        else
            echo "wazuh-yara: ERROR - Could not delete: $FILENAME" >> "$LOG_FILE"
            exit 1
        fi
    else
        echo "wazuh-yara: ERROR - Not deleting non-regular file or symlink: $FILENAME" >> "$LOG_FILE"
        exit 1
    fi
fi

exit 0
