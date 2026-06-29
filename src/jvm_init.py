import glob
import logging
import os
import jpype

logger = logging.getLogger(__name__)


def _find_mpxj_jars():
    try:
        import mpxj as _mpxj_pkg
        lib_dir = os.path.join(os.path.dirname(_mpxj_pkg.__file__), "lib")
        jars = glob.glob(os.path.join(lib_dir, "*.jar"))
        if jars:
            return jars
    except ImportError:
        pass
    return []


def start_jvm_if_needed():
    """
    Start JVM for MPXJ with the mpxj classpath. Must be called after
    Gunicorn forks workers, never at module import time. Safe to call
    multiple times.
    """
    if not jpype.isJVMStarted():
        jars = _find_mpxj_jars()
        if not jars:
            raise RuntimeError(
                "No MPXJ JARs found. Ensure the 'mpxj' package (v16+) is installed."
            )
        jpype.startJVM(
            "-Djava.awt.headless=true",
            "-Xms256m",
            "-Xmx512m",
            convertStrings=True,
            classpath=jars,
        )
        logger.info(f"JVM started with {len(jars)} MPXJ JARs")
