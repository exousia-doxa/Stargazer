package net.astrometry;

import com.chaquo.python.Kwarg;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

public class JNI {
    static Python python = Python.getInstance();
    static {
        try {
            System.loadLibrary("astrometry");
        } catch (UnsatisfiedLinkError e) {
            // Library not found yet; will fail when native methods are called
        }
    }

    public static synchronized native int solveField(String[] args, double[] results);

    // This function is called from libastrometry.so via JNI
    public static void removelines(String infile, String outfile, String xcol, String ycol) {
        PyObject module = python.getModule("astrometry.util.removelines");
        module.callAttr("removelines", infile, outfile, new Kwarg("xcol", xcol), new Kwarg("ycol", ycol));
    }

    // This function is called from libastrometry.so via JNI
    public static void uniformize(String infile, String outfile, int n, String xcol, String ycol) {
        PyObject module = python.getModule("astrometry.util.uniformize");
        module.callAttr("uniformize", infile, outfile, n, new Kwarg("xcol", xcol), new Kwarg("ycol", ycol));
    }
}
