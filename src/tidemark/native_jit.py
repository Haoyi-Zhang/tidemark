"""Native execution for generated, owned scalar modules, not external inputs."""
import ctypes
from llvmlite import binding as llvm


def initialize():
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    llvm.check_jit_execution()


def execute(ir, inputs, optimize=False):
    """Verify, compile, call and dispose one module. No external symbols/calls.

    Callers supply only lower() output or the fixed arithmetic countermodel.
    This harness is not an authorization boundary for untrusted LLVM.
    """
    module = llvm.parse_assembly(ir.decode("ascii"))
    module.verify()
    target = llvm.Target.from_default_triple()
    machine = target.create_target_machine(opt=0)
    module.triple = llvm.get_default_triple()
    module.data_layout = str(machine.target_data)
    if optimize:
        with llvm.create_pipeline_tuning_options(speed_level=2) as pto:
            with llvm.create_pass_builder(machine, pto) as pb:
                with pb.getModulePassManager() as pm:
                    pm.run(module, pb)
        module.verify()
    normalized = str(module)
    # Retain machine-code object bytes as reproducibility evidence, not a
    # watermark-extraction channel or a measured deployment footprint.
    obj = machine.emit_object(module)
    with llvm.create_mcjit_compiler(module, machine) as engine:
        engine.finalize_object()
        address = engine.get_function_address("run")
        if not address:
            raise RuntimeError("owned function not emitted")
        arity = len(inputs[0]) if inputs else 0
        function = ctypes.CFUNCTYPE(ctypes.c_int64, *([ctypes.c_int64] * arity))(address)
        values = [int(function(*args)) for args in inputs]
    return values, normalized, obj
