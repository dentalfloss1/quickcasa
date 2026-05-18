#!/bin/bash
#SBATCH --job-name=casa_image_ms
#SBATCH --partition=batch
#SBATCH --time=2-00:00:00
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --output=/lustre/aoc/observers/nm-11514/data/%x_%j.out
#SBATCH --error=/lustre/aoc/observers/nm-11514/data/%x_%j.err

set -euo pipefail

BASE_DIR="/lustre/aoc/observers/nm-11514/data/"
JOB_ID="${SLURM_JOB_ID:-local}"
SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"

echo "Job started: $(date)"
echo "Job ID: ${JOB_ID}"
echo "Node: $(hostname)"
echo "BASE_DIR: ${BASE_DIR}"
echo "Submit directory: ${SUBMIT_DIR}"

usage() {
    cat <<EOF
Usage:
  sbatch $(basename "$0") <ms-path-or-glob> [<ms-path-or-glob> ...] [-- <image-script-args> ...]

Examples:
  sbatch $(basename "$0") "/lustre/aoc/observers/nm-11514/data/**/*.ms"
  sbatch $(basename "$0") "/lustre/aoc/observers/nm-11514/data/**/*.ms" -- --band C --dry-run

Inputs must be MeasurementSet directories ending in .ms. Tarballs are not accepted.
With no --field argument, image_140515A_simple.py selects only fields with TARGET intent.
EOF
}

# Require the generalized imaging script. IMAGE_SCRIPT_SOURCE may be set at
# submission time; otherwise prefer the submit directory, then HOME.
IMAGE_SCRIPT="image_140515A_simple.py"
IMAGE_SCRIPT_SOURCE="${IMAGE_SCRIPT_SOURCE:-${SUBMIT_DIR}/${IMAGE_SCRIPT}}"
if [[ ! -f "${IMAGE_SCRIPT_SOURCE}" && -f "${HOME}/${IMAGE_SCRIPT}" ]]; then
    IMAGE_SCRIPT_SOURCE="${HOME}/${IMAGE_SCRIPT}"
fi

# Inputs before "--" are MeasurementSet paths/globs. Arguments after "--" are
# passed through to image_140515A_simple.py.
DATA_INPUTS=()
IMAGE_ARGS=()
IN_IMAGE_ARGS=0
for ARG in "$@"; do
    if [[ "${ARG}" == "--" ]]; then
        IN_IMAGE_ARGS=1
        continue
    fi

    if [[ "${IN_IMAGE_ARGS}" -eq 1 ]]; then
        IMAGE_ARGS+=("${ARG}")
    else
        DATA_INPUTS+=("${ARG}")
    fi
done

if [[ "${#DATA_INPUTS[@]}" -eq 0 ]]; then
    echo "ERROR: No .ms input or glob provided." >&2
    usage >&2
    exit 2
fi

add_ms_input() {
    local input_path="${1%/}"

    if [[ -d "${input_path}" && "${input_path}" == *.ms ]]; then
        MS_INPUTS+=("${input_path}")
    elif [[ -e "${input_path}" ]]; then
        echo "ERROR: Inputs must be MeasurementSet directories ending in .ms: ${input_path}" >&2
        exit 1
    fi
}

shopt -s globstar nullglob
MS_INPUTS=()
for INPUT in "${DATA_INPUTS[@]}"; do
    if [[ -d "${INPUT}" || -e "${INPUT}" ]]; then
        add_ms_input "${INPUT}"
        continue
    fi

    MATCHED=0
    while IFS= read -r MATCH; do
        MATCHED=1
        add_ms_input "${MATCH}"
    done < <(compgen -G "${INPUT}")

    if [[ "${MATCHED}" -eq 0 ]]; then
        echo "ERROR: No .ms directories matched input glob: ${INPUT}" >&2
        exit 1
    fi
done

if [[ "${#MS_INPUTS[@]}" -eq 0 ]]; then
    echo "ERROR: No .ms directories matched input: ${DATA_INPUTS[*]}" >&2
    exit 1
fi

mapfile -t MS_INPUTS < <(printf '%s\n' "${MS_INPUTS[@]}" | sort -u)

echo "Matched MS inputs: ${#MS_INPUTS[@]}"
if [[ "${#IMAGE_ARGS[@]}" -gt 0 ]]; then
    echo "Image script args: ${IMAGE_ARGS[*]}"
else
    echo "Image script args: default TARGET intent selection"
fi

for MS_INPUT in "${MS_INPUTS[@]}"; do
    MS_INPUT="${MS_INPUT%/}"
    MS_DIR="$(cd "$(dirname "${MS_INPUT}")" && pwd)"
    MS_NAME="$(basename "${MS_INPUT}")"

    cd "${MS_DIR}"

    if [[ ! -e "${IMAGE_SCRIPT}" && ! -L "${IMAGE_SCRIPT}" ]]; then
        if [[ ! -f "${IMAGE_SCRIPT_SOURCE}" ]]; then
            echo "ERROR: Imaging script source does not exist: ${IMAGE_SCRIPT_SOURCE}" >&2
            exit 1
        fi

        ln -s "${IMAGE_SCRIPT_SOURCE}" "${IMAGE_SCRIPT}"
    fi

    echo ""
    echo "Working directory: ${MS_DIR}"
    echo "Running imaging on MS: ${MS_NAME}"
    echo "Images will be written under: ${MS_DIR}/images"

    xvfb-run casa-vla --nogui --log2term -c "${IMAGE_SCRIPT}" "${MS_NAME}" "${IMAGE_ARGS[@]}"
done

echo "Job finished: $(date)"
