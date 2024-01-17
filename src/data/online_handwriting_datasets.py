from pathlib import Path
import logging

import h5py


class OnlineHandwritingDataset:

    # TODO: Should be compatible with PyTorch dataset and/or
    #       HuggingFace Dataset where I prefer the former.
    #
    #       The existing online handwriting datasets tend to be
    #       relatively small so that they easily fit in RAM memory.
    #
    #       Caching them is useful nevertheless.

    """
    Class to represent an online handwriting dataset.

    This class serves as dataset provider to other machine learning library dataset classes
    like those from PyTorch or PyTorch Lightning.
    """

    FAILED_SAMPLE = -1

    # Methods that might be useful:
    # - some visualisation methods - plot image and also animated 2d and 3d video

    def __init__(self, path=None, logger=None):
        """
        A class to unify multiple datasets in a modular way.

        The data is stored in the `data` field and is organised in a list that stores
        a dict of all features. This format is well suitable for storing time series as
        features. This class therefore only stores datasets that can fit in memory. This
        is an example for the IAMonDB format:
            data = [
                    { 'x': [...], 'y': [...], 't': [...], ..., 'label': ..., 'sample_name': ..., ... }, 
                    ...
                   ]

        The input and output data for subsequent model trainings can easily be derived
        based on the features in each sample. Each sample should have the same features.
        This is not checked.

        :param path: Path to load raw data from.
        """
        self.path = path
        if logger is None:
            self.logger = logging.getLogger('OnlineHandwritingDataset')
        else:
            self.logger = logger

        self.logger.info('Dataset created')

        self.data = []

    def load_data(self) -> None:
        """
        Needs to be implemented in subclasses.
        """
        raise NotImplementedError

    def set_data(self, data):
        self.data = data

    def to_disc(self, path: Path) -> None:
        """
        Store OnlineHandwritingDataset to disc.

        The OnlineHandwritingDataset is stored as HDF5 file of the structure:
        - one group per sample
        - one dataset per feature; those can be a time series as well as a single value

        :param path: Path to save dataset to.
        """
        with h5py.File(path, 'w') as f:
            for i, sample in enumerate( self.data ):
                group = f.create_group(f'sample_{i}')
                for key, value in sample.items():
                    group.create_dataset(key, data=value)

    def from_disc(self, path: Path) -> None:
        """
        Load OnlineHandwritingDataset from disc.

        The dataset must be in the format that is used in `to_disc()` to save the dataset.
        The data from disc is appended to the `data` attribute.

        :param path: Path to load dataset from.
        """
        with h5py.File(path, 'r') as f:
            for group_name in f:
                group = f[group_name]
                storage = {}
                for feature in group:
                    feature_dataset = group[feature]
                    value = feature_dataset[()]
                    if type(value) == bytes: # Convert bytes to string
                        value = value.decode('utf-8')
                    storage[feature] = value
                self.data.append(storage)

    def map(self, fct, logger=None):
        """
        Applies a function to each sample and creates a new Dataset based on that.

        If the function indicates that the transformation of the sample has failed,
        then it is not added to the list of mapped samples.

        :param fct: The function that is applied. Its signature is `fct(sample)` with
                    `sample` being an element from `self.data`.
        :param logger: Logger that is used for resulting new dataset.
        :returns: New dataset.
        """
        new_dataset = OnlineHandwritingDataset(logger)
        data = []
        for sample in self.data:
            sample_mapped = fct( sample )
            if sample_mapped != self.FAILED_SAMPLE:
                data.append( sample_mapped )
        new_dataset.set_data( data )
        return new_dataset

    def fit_bezier_curve(self):
        # TODO.
        # Idea: Fit bezier curves recursively just as [Carbune2020] does.
        raise NotImplementedError

class IAMonDB_Dataset(OnlineHandwritingDataset):

    # TODO: Should be compatible with the plain IAMonDB
    #       folder structure.

    pass

class XournalPagewiseDataset(OnlineHandwritingDataset):

    # TODO: load an online text from pages of a Xournal file

    # TODO: This class allows easy testing on real data.

    pass
