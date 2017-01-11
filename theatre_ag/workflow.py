"""
@author twsswt
"""

import inspect


def default_cost(cost=0):
    def workflow_decorator(func):
        func.default_cost = cost
        return func
    return workflow_decorator


_workflow_classes = set()


def allocate_workflow_to(actor, workflow, logging=True):
    """
    Allocates the workflow to the specified actor for timing synchronization purposes.  The members of the workflow are
    recursively inspected.  Any member with the class attribute 'is_workflow' is also allocated to this actor if it has
    not previously been allocated to another actor.
    """
    workflow.actor = actor
    workflow.logging = logging

    workflow_class = workflow.__class__
    if workflow_class not in _workflow_classes:
        treat_as_workflow(workflow_class)
        _workflow_classes.add(workflow_class)

    for name, member in inspect.getmembers(workflow):
        if hasattr(member.__class__, 'is_workflow') and not hasattr(member, 'actor'):
            allocate_workflow_to(actor, member, logging)


def treat_as_workflow(workflow_class):
    """
    Modifies the specified class to intercept __getattribute__ calls for task methods of a workflow, and synchronise
    their execution with an actor.  The underlying 'reference' __getattribute__ method is retained and used to access
    the underlying workflow task method for execution within the synchronization machinery.
    """

    reference_get_attr = workflow_class.__getattribute__

    def __tracked_getattribute(self, item):

        attribute = reference_get_attr(self, item)

        if hasattr(attribute, 'func_name') and attribute.func_name[0:2] == '__':
            return attribute

        elif inspect.ismethod(attribute) or inspect.isfunction(attribute):

            def sync_wrap(*args, **kwargs):

                if hasattr(self, 'actor'):

                    actor = self.actor

                    actor.busy.acquire()

                    actor.log_task_initiation(self, attribute, args)

                    # TODO Pass function name and indicative cost to a cost calculation function.
                    if hasattr(attribute, 'default_cost'):
                        actor.incur_delay(attribute.default_cost)

                    actor.wait_for_turn()

                    if inspect.ismethod(attribute):
                        result = attribute.im_func(self, *args, **kwargs)
                    else:
                        result = attribute(*args, **kwargs)

                    actor.log_task_completion()

                    actor.busy.release()
                    return result

                else:
                    return attribute.im_func(self, *args, **kwargs)

            if inspect.ismethod(attribute):
                sync_wrap.func_name = attribute.im_func.func_name
            else:
                sync_wrap.func_name = attribute.func_name

            return sync_wrap

        else:
            return attribute

    workflow_class.__getattribute__ = __tracked_getattribute


class Idling(object):

    """
    A workflow that allows an actor to waste a turn.
    """

    is_workflow = True

    @default_cost(0)
    def idle_for(self, duration):
        for _ in range(0, duration):
            self.idle()

    @default_cost(0)
    def idle_until(self, allocated_task):
        while not allocated_task.completed:
            self.idle()

    @default_cost(1)
    def idle(self):
        pass
