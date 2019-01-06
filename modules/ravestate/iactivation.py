# Interface of state activation towards spike
# Spike interface towards state activation

from typing import Set, Optional, Generator


class ISpike:
    """
    Base interface class for spikes.
    """

    def name(self) -> str:
        """
        Returns the name of this spike's signal.
        """
        pass

    def wipe(self, already_wiped_in_causal_group: bool=False) -> None:
        """
        Called either in Context run loop when the spike is found to be stale
         (with wiped_in_causal_group=True), or in Context.wipe(signal_inst),
         or by parent (recursively).
        After this function is called, the spike should be cleaned up by GC.
        :param already_wiped_in_causal_group: Boolean which indicates, whether wiped(signal_inst)
         must still be called on the group to make sure sure that no dangling references
         to the spike are maintained by any state activations.
        """
        pass

    def has_offspring(self):
        """
        Called by CausalGroup.stale(spike).
        :return: True if the spike has active offspring, false otherwise.
        """
        pass

    def offspring(self) -> Generator['Spike', None, None]:
        """
        Recursively yields this spike's offspring and it's children's offspring.
        :return: All of this spike's offspring spikes.
        """


class IActivation:
    """
    Base interface class for state activations.
    """

    name: str

    def write_props(self) -> Set[str]:
        """
        Return's the set of the activation's write-access property names.
        """
        pass

    def specificity(self) -> float:
        """
        Returns the lowest specificity among the specificity values of the
         activation's conjunct contraints. The specificity for a single conjunction
         is calculated as the sum of it's component signal's specificities,
         which in turn is calculated as one over the signal's subscriber count.
        """
        pass

    def dereference(self, *, spike: Optional[ISpike]=None, reacquire: bool=False, reject: bool=False) -> None:
        """
        Notify the activation, that a single or all spike(s) are not available
         anymore, and should therefore not be referenced anymore by the activation.
        This is called by ...
         ... context when a state is deleted.
         ... causal group, when a referenced signal was consumed for a required property.
         ... causal group, when a referenced signal was wiped.
         ... this activation (with reacquire=True), if it gives in to activation pressure.
        :param spike: The spike that should be forgotten by the activation, or
         none, if all referenced spikes should be forgotten.
        :param reacquire: Flag which tells the function, whether for every rejected
         spike, the activation should hook into context for reacquisition
         of a replacement spike.
        :param reject: Flag which controls, whether de-referenced spikes
         should be explicitely rejected through their causal groups.
        """
        pass

    def pressure(self, give_me_up: ISpike):
        """
        Called by CausalGroup, to pressure the activation to
         make a decision on whether it is going to retain a reference
         to the given spike, given that there is a lower-
         specificity activation which is ready to run.
        """
        # TODO: Implement Activation.pressure(). Impl will use Context.lowest_upper_bound_eta(signals)
        #  to get a time estimate on when progress on the activations constraints
        #  is to be expected. If progress is not made within the predicted
        #  time period, the activation is going to auto-eliminate for the pressured
        #  spikes.
