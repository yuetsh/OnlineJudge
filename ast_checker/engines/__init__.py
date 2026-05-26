from .function_call import CountFunctionCallEngine, MustCallFunctionEngine, MustNotCallFunctionEngine
from .method_call import MustCallMethodEngine, MustNotCallMethodEngine
from .nesting import MustHaveNestingEngine
from .node_count import CountNodeEngine
from .node_exists import MustExistNodeEngine, MustNotExistNodeEngine
from .operator import MustUseOperatorEngine

ENGINES = {
    "must_exist_node": MustExistNodeEngine(),
    "must_not_exist_node": MustNotExistNodeEngine(),
    "count_node": CountNodeEngine(),
    "must_call_function": MustCallFunctionEngine(),
    "must_not_call_function": MustNotCallFunctionEngine(),
    "count_function_call": CountFunctionCallEngine(),
    "must_call_method": MustCallMethodEngine(),
    "must_not_call_method": MustNotCallMethodEngine(),
    "must_use_operator": MustUseOperatorEngine(),
    "must_have_nesting": MustHaveNestingEngine(),
}


def get_engine(name: str):
    return ENGINES.get(name)
