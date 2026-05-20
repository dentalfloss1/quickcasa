#!/bin/bash
#SBATCH --job-name=casa_doall_array
#SBATCH --partition=batch
#SBATCH --time=2-00:00:00
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --array=1-7
#SBATCH --output=/lustre/aoc/observers/nm-11514/data/%x_%A_%a.out
#SBATCH --error=/lustre/aoc/observers/nm-11514/data/%x_%A_%a.err

set -euo pipefail

BASE_DIR="/lustre/aoc/observers/nm-11514/data/"
TASK_ID="${SLURM_ARRAY_TASK_ID:-1}"
JOB_ID="${SLURM_JOB_ID:-local}"

echo "Job started: $(date)"
echo "Job ID: ${JOB_ID}"
echo "Array task ID: ${TASK_ID}"
echo "Node: $(hostname)"
echo "BASE_DIR: ${BASE_DIR}"

# Require the automated doall calibration/imaging script.
DOALL_SCRIPT="doall_auto.py"
DOALL_SCRIPT_SOURCE="${HOME}/${DOALL_SCRIPT}"


# Find tarred MeasurementSets from input globs or paths. Quote recursive globs when
# submitting with sbatch so they expand on the compute node.
if [[ "$#" -eq 0 ]]; then
    echo "No *.ms.tgz input provided; defaulting to ${BASE_DIR}/**/*.ms.tgz"
    set -- "${BASE_DIR}/**/*.ms.tgz"
fi

shopt -s globstar nullglob
MS_TGZS=()
for INPUT in "$@"; do
    if [[ -f "${INPUT}" ]]; then
        MS_TGZS+=("${INPUT}")
        continue
    fi

    while IFS= read -r MATCH; do
        MS_TGZS+=("${MATCH}")
    done < <(compgen -G "${INPUT}")
done

if [[ "${#MS_TGZS[@]}" -eq 0 ]]; then
    echo "ERROR: No *.ms.tgz files matched input: $*" >&2
    exit 1
fi

mapfile -t MS_TGZS < <(printf '%s\n' "${MS_TGZS[@]}" | sort -u)

if (( TASK_ID < 1 || TASK_ID > ${#MS_TGZS[@]} )); then
    echo "ERROR: Array task ${TASK_ID} is outside matched file range 1-${#MS_TGZS[@]}" >&2
    exit 1
fi

MS_TGZ="${MS_TGZS[$((TASK_ID - 1))]}"
MS_DIR="$(cd "$(dirname "${MS_TGZ}")" && pwd)"
MS_TGZ_BASENAME="$(basename "${MS_TGZ}")"

cd "${MS_DIR}"

if [[ ! -e "${DOALL_SCRIPT}" && ! -L "${DOALL_SCRIPT}" ]]; then
    if [[ ! -f "${DOALL_SCRIPT_SOURCE}" ]]; then
        echo "ERROR: doall script source does not exist: ${DOALL_SCRIPT_SOURCE}" >&2
        exit 1
    fi

    ln -s "${DOALL_SCRIPT_SOURCE}" "${DOALL_SCRIPT}"
fi

# Expected extracted MS name.
MS_NAME="${MS_TGZ_BASENAME%.tgz}"

echo "Matched MS tarballs: ${#MS_TGZS[@]}"
echo "Working directory: ${MS_DIR}"
echo "MS tarball: ${MS_TGZ_BASENAME}"
echo "Expected MS: ${MS_NAME}"

# Untar only if the MS directory is not already present.
if [[ ! -d "${MS_NAME}" ]]; then
    echo "Extracting ${MS_TGZ_BASENAME}"
    tar -xzvf "${MS_TGZ_BASENAME}"
else
    echo "MS directory already exists; skipping extraction: ${MS_NAME}"
fi

if [[ ! -d "${MS_NAME}" ]]; then
    echo "ERROR: Expected extracted MS directory does not exist: ${MS_NAME}" >&2
    exit 1
fi

START_DELAY=$(( (TASK_ID - 1) * 120 ))
echo "Sleeping ${START_DELAY} seconds before launching CASA"
sleep "${START_DELAY}"

echo "doall script: ${DOALL_SCRIPT}"
echo "Running automated calibration/imaging on MS: ${MS_NAME}"

xvfb-run casa-vla --nogui --log2term -c "${DOALL_SCRIPT}" "${MS_NAME}"

echo "Job finished: $(date)"
