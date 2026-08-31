import java.io.File;

import org.openlca.core.matrix.solvers.mkl.MKL;
import org.openlca.ipc.Server;

/** Headless openLCA IPC server; loads MKL before starting. */
public final class OlcaIpcServer {

    private OlcaIpcServer() {
    }

    public static void main(String[] args) throws Exception {
        loadMkl();
        Server.main(args);
    }

    private static void loadMkl() {
        String dirProp = System.getProperty("olca.mkl.dir");
        if (dirProp == null || dirProp.isBlank()) {
            System.out.println("[OlcaIpcServer] -Dolca.mkl.dir not set; using pure Java solver.");
            return;
        }

        File dir = new File(dirProp);
        boolean ok = false;
        try {
            if (MKL.isLibraryDir(dir)) {
                ok = MKL.loadFrom(dir);
            } else if (dir.getParentFile() != null && MKL.isLibraryDir(dir.getParentFile())) {
                ok = MKL.loadFrom(dir.getParentFile());
            } else {
                ok = MKL.loadFrom(dir);
            }
        } catch (Throwable t) {
            System.out.println("[OlcaIpcServer] MKL load error: " + t);
        }

        System.out.println("[OlcaIpcServer] MKL dir=" + dir.getAbsolutePath()
                + "  loadFrom=" + ok + "  isLoaded=" + MKL.isLoaded());
    }
}
