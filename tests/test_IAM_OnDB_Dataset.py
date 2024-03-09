from pathlib import Path

import pytest
import numpy as np

from src.data.online_handwriting_datasets import IAM_OnDB_Dataset


PATH = Path('data/datasets/IAM-OnDB') # Needs to be parameterised

@pytest.mark.martin
def test_construction_with_limit():

    limit = 5

    ds = IAM_OnDB_Dataset(path=PATH, transform=None, limit=limit)

    assert len(ds) == limit

@pytest.mark.martin
@pytest.mark.slow
def test_construction_no_limit():

    ds = IAM_OnDB_Dataset(path=PATH, transform=None, limit=-1)

    length = 12187 # Determined empirically

    assert len(ds) == length

@pytest.mark.martin
@pytest.mark.slow
def test_correctness_manually(tmp_path: Path):
    # This saves samples to files so that one can inspect the correctness of the
    # dataset manually. Enabling the pytest setting `-s` allows one to see where
    # the files were saved temporarily.

    NR_SAMPLES = 100
    LIMIT = -1

    print()
    print(f'Samples saved at: "{tmp_path}"')
    print()

    ds = IAM_OnDB_Dataset(path=PATH, transform=None, limit=LIMIT)

    # Get NR_SAMPLES reproducible random draws
    rng = np.random.default_rng(1337)
    index_list = np.arange(0, len(ds))
    rng.shuffle(index_list)
    index_list = index_list[:NR_SAMPLES]

    for iam_index in index_list:
        sample_name = ds[iam_index]['sample_name']
        ds.plot_sample_to_image_file(iam_index, tmp_path / Path(f'{sample_name}.png'))