# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2018.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Model for schema-conformant Results."""

from qiskit.circuit.quantumcircuit import QuantumCircuit
from qiskit.pulse.schedule import Schedule
from qiskit.exceptions import QiskitError
from qiskit.quantum_info.states import state_to_counts

from qiskit.validation.base import BaseModel, bind_schema
from qiskit.result import postprocess
from qiskit.qobj.utils import MeasLevel
from .models import ResultSchema


@bind_schema(ResultSchema)
class Result(BaseModel):
    """Model for Results.

    Please note that this class only describes the required fields. For the
    full description of the model, please check ``ResultSchema``.

    Attributes:
        backend_name (str): backend name.
        backend_version (str): backend version, in the form X.Y.Z.
        qobj_id (str): user-generated Qobj id.
        job_id (str): unique execution id from the backend.
        success (bool): True if complete input qobj executed correctly. (Implies
            each experiment success)
        results (list[ExperimentResult]): corresponding results for array of
            experiments of the input qobj
    """

    def __init__(self, backend_name, backend_version, qobj_id, job_id, success,
                 results, **kwargs):
        self.backend_name = backend_name
        self.backend_version = backend_version
        self.qobj_id = qobj_id
        self.job_id = job_id
        self.success = success
        self.results = results

        super().__init__(**kwargs)

    def data(self, experiment=None):
        """Get the raw data for an experiment.

        Note this data will be a single classical and quantum register and in a
        format required by the results schema. We recommend that most users use
        the get_xxx method, and the data will be post-processed for the data type.

        Args:
            experiment (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment. Several types are accepted for convenience::
                * str: the name of the experiment.
                * QuantumCircuit: the name of the circuit instance will be used.
                * Schedule: the name of the schedule instance will be used.
                * int: the position of the experiment.
                * None: if there is only one experiment, returns it.

        Returns:
            dict: A dictionary of results data for an experiment. The data
            depends on the backend it ran on and the settings of `meas_level`,
            `meas_return` and `memory`.

            QASM backends return a dictionary of dictionary with the key
            'counts' and  with the counts, with the second dictionary keys
            containing a string in hex format (``0x123``) and values equal to
            the number of times this outcome was measured.

            Statevector backends return a dictionary with key 'statevector' and
            values being a list[list[complex components]] list of 2^n_qubits
            complex amplitudes. Where each complex number is represented as a 2
            entry list for each component. For example, a list of
            [0.5+1j, 0-1j] would be represented as [[0.5, 1], [0, -1]].

            Unitary backends return a dictionary with key 'unitary' and values
            being a list[list[list[complex components]]] list of
            2^n_qubits x 2^n_qubits complex amplitudes in a two entry list for
            each component. For example if the amplitude is
            [[0.5+0j, 0-1j], ...] the value returned will be
            [[[0.5, 0], [0, -1]], ...].

            The simulator backends also have an optional key 'snapshots' which
            returns a dict of snapshots specified by the simulator backend.
            The value is of the form dict[slot: dict[str: array]]
            where the keys are the requested snapshot slots, and the values are
            a dictionary of the snapshots.

        Raises:
            QiskitError: if data for the experiment could not be retrieved.
        """
        try:
            return self._get_experiment(experiment).data.to_dict()
        except (KeyError, TypeError):
            raise QiskitError('No data for experiment "{0}"'.format(experiment))

    def get_memory(self, experiment=None):
        """Get the sequence of memory states (readouts) for each shot
        The data from the experiment is a list of format
        ['00000', '01000', '10100', '10100', '11101', '11100', '00101', ..., '01010']

        Args:
            experiment (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment, as specified by ``data()``.

        Returns:
            List[str] or np.ndarray: Either the list of each outcome, formatted according to
                registers in circuit or a complex numpy np.darray with shape:

                ============  =============  =====
                `meas_level`  `meas_return`  shape
                ============  =============  =====
                0             `single`       np.ndarray[shots, memory_slots, memory_slot_size]
                0             `avg`          np.ndarray[memory_slots, memory_slot_size]
                1             `single`       np.ndarray[shots, memory_slots]
                1             `avg`          np.ndarray[memory_slots]
                2             `memory=True`  list
                ============  =============  =====

        Raises:
            QiskitError: if there is no memory data for the circuit.
        """
        try:
            exp_result = self._get_experiment(experiment)

            try:  # header is not available
                header = exp_result.header.to_dict()
            except (AttributeError, QiskitError):
                header = None

            meas_level = exp_result.meas_level

            memory = self.data(experiment)['memory']

            if meas_level == MeasLevel.CLASSIFIED:
                return postprocess.format_level_2_memory(memory, header)
            elif meas_level == MeasLevel.KERNELED:
                return postprocess.format_level_1_memory(memory)
            elif meas_level == MeasLevel.RAW:
                return postprocess.format_level_0_memory(memory)
            else:
                raise QiskitError('Measurement level {0} is not supported'.format(meas_level))

        except KeyError:
            raise QiskitError('No memory for experiment "{0}".'.format(experiment))

    def get_counts(self, experiment=None):
        """Get the histogram data of an experiment.

        Args:
            experiment (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment, as specified by ``get_data()``.

        Returns:
            dict[str:int]: a dictionary with the counts for each qubit, with
                the keys containing a string in binary format and separated
                according to the registers in circuit (e.g. ``0100 1110``).
                The string is little-endian (cr[0] on the right hand side).

        Raises:
            QiskitError: if there are no counts for the experiment.
        """
        exp = self._get_experiment(experiment)
        try:
            header = exp.header.to_dict()
        except (AttributeError, QiskitError):  # header is not available
            header = None

        if 'counts' in self.data(experiment).keys():
            return postprocess.format_counts(self.data(experiment)['counts'],
                                             header)
        elif 'statevector' in self.data(experiment).keys():
            vec = postprocess.format_statevector(self.data(experiment)['statevector'])
            return state_to_counts(vec)
        else:
            raise QiskitError('No counts for experiment "{0}"'.format(experiment))

    def get_statevector(self, experiment=None, decimals=None):
        """Get the final statevector of an experiment.

        Args:
            experiment (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment, as specified by ``data()``.
            decimals (int): the number of decimals in the statevector.
                If None, does not round.

        Returns:
            list[complex]: list of 2^n_qubits complex amplitudes.

        Raises:
            QiskitError: if there is no statevector for the experiment.
        """
        try:
            return postprocess.format_statevector(self.data(experiment)['statevector'],
                                                  decimals=decimals)
        except KeyError:
            raise QiskitError('No statevector for experiment "{0}"'.format(experiment))

    def get_unitary(self, experiment=None, decimals=None):
        """Get the final unitary of an experiment.

        Args:
            experiment (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment, as specified by ``data()``.
            decimals (int): the number of decimals in the unitary.
                If None, does not round.

        Returns:
            list[list[complex]]: list of 2^n_qubits x 2^n_qubits complex
                amplitudes.

        Raises:
            QiskitError: if there is no unitary for the experiment.
        """
        try:
            return postprocess.format_unitary(self.data(experiment)['unitary'],
                                              decimals=decimals)
        except KeyError:
            raise QiskitError('No unitary for experiment "{0}"'.format(experiment))

    def _get_experiment(self, key=None):
        """Return a single experiment result from a given key.

        Args:
            key (str or QuantumCircuit or Schedule or int or None): the index of the
                experiment, as specified by ``data()``.

        Returns:
            ExperimentResult: the results for an experiment.

        Raises:
            QiskitError: if there is no data for the experiment, or an unhandled
                error occurred while fetching the data.
        """
        # Automatically return the first result if no key was provided.
        if key is None:
            if len(self.results) != 1:
                raise QiskitError(
                    'You have to select a circuit or schedule when there is more than '
                    'one available')
            key = 0

        # Key is a QuantumCircuit/Schedule or str: retrieve result by name.
        if isinstance(key, (QuantumCircuit, Schedule)):
            key = key.name
        # Key is an integer: return result by index.
        if isinstance(key, int):
            exp = self.results[key]
        else:
            try:
                # Look into `result[x].header.name` for the names.
                exp = next(result for result in self.results
                           if getattr(getattr(result, 'header', None),
                                      'name', '') == key)
            except StopIteration:
                raise QiskitError('Data for experiment "%s" could not be found.' %
                                  key)

        # Check that the retrieved experiment was successful
        if getattr(exp, 'success', False):
            return exp
        # If unsuccessful check experiment and result status and raise exception
        result_status = getattr(self, 'status', 'Result was not successful')
        exp_status = getattr(exp, 'status', 'Experiment was not successful')
        raise QiskitError(result_status, ", ", exp_status)
