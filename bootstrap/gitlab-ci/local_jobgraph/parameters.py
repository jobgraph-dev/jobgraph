from voluptuous import Required

from jobgraph.parameters import extend_parameters_schema

extend_parameters_schema(
    {
        Required("some_extra_parameter"): str,
    }
)


def get_decision_parameters(graph_config, parameters):
    # Here you can provide additional parameters that don't exist in
    # upstream jobgraph.
    parameters.setdefault("some_extra_parameter", "some_extra_value")
