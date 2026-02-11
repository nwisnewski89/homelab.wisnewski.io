#!/usr/bin/env bash
set -u

INPUT_DIR="${INPUT_DIR:-}"
OUTPUT_DIR="${OUTPUT_DIR:-}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
FOO_SCRIPT="${FOO_SCRIPT:-foo}"
WORK_DIR="${WORK_DIR:-}"

if [[ -z "$INPUT_DIR" || -z "$OUTPUT_DIR" ]]; then
  echo "INPUT_DIR and OUTPUT_DIR must be set." >&2
  exit 1
fi

if [[ -z "$WORK_DIR" ]]; then
  WORK_DIR="${INPUT_DIR}/.processing"
fi

mkdir -p "$OUTPUT_DIR" "$WORK_DIR"
shopt -s nullglob

process_file() {
  local file="$1"
  local base work_file type body id status tmp

  base="$(basename "$file")"
  work_file="${WORK_DIR}/${base}"

  if ! mv "$file" "$work_file"; then
    echo "Failed to move ${file} to ${work_file}" >&2
    return 1
  fi

  type="$(jq -r '.type // empty' "$work_file")"
  body="$(jq -r '.body // empty' "$work_file")"
  id="$(jq -r '.id // empty' "$work_file")"

  status="fail"
  if [[ "$type" == "foo" ]]; then
    TYPE="$type" BODY="$body" ID="$id" "$FOO_SCRIPT"
    if [[ $? -eq 0 ]]; then
      status="pass"
    else
      status="fail"
    fi
  elif [[ -n "$type" ]]; then
    status="fail"
  else
    status="fail"
  fi

  tmp="$(mktemp "${WORK_DIR}/${base}.XXXX")"
  jq --arg status "$status" '. + {status: $status}' "$work_file" > "$tmp"
  mv "$tmp" "${OUTPUT_DIR}/${base}"
  rm -f "$work_file"
}

while true; do
  for file in "${INPUT_DIR}"/*.json; do
    [[ -e "$file" ]] || break
    process_file "$file"
  done
  sleep "$POLL_INTERVAL"
done
