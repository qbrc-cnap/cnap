## CNAP reproducibility features

CNAP was built as a platform to strongly enforce the reproducibility of analysis pipelines.  It accomplishes this through three main mechanisms:

1. **Required git integration**

    To "ingest" an analysis process into CNAP, we require that all the workflow files (WDL files, etc.) are version-controlled in git and available from a remote github repository.  The repository must be "self-contained" and include everything necessary to execute the process.  The ingestion process is started by providing the "clone" URL to the CNAP admin dashboard.

    During the ingestion process, the unique git commit hash is saved to the CNAP database.  This identifier (and the github repository) is provided to the analysis client upon completion of the analysis workflow.  The repository and commit ID allow the client to recall the exact workflow at a later time.  

      

2. **Containerization**
    
    While the git integration above enforces that the pipeline content (i.e. the code) is traceable, it does not control for the computing environment in which the process is performed.  CNAP handles this via Docker containers.  
    
    By default, the Cromwell workflow engine we employ uses either local or remote (e.g. Dockerhub) Docker images to execute the WDL-based tasks.  However, there is no mechanism to enforce that the Docker images employed are the same each time; indeed, one may use an image with the same tag (e.g. `docker.io/userX/imageY:v0.1`) without any guarantee that the container has not been changed.

    Therefore, CNAP performs regular queries of the Docker "digest" (i.e. a hash like `sha256:7cb3...`) for each Docker image used in a workflow.  Upon execution of the workflow, CNAP queries Dockerhub for the set of image digests.  These are included as part of the final workflow outputs so that the exact Docker image may be pulled at a later date (i.e. `docker pull <image_name>@sha256:7cb3...`).

3. **Independence of workflows**

    Although the git repository contains all the necessary files for a "CNAP-style" workflow, the WDL files themselves are completely independent of CNAP and may be used anywhere else that works with WDL-based workflows.  That is,

    $$
    \textrm{(Valid WDL workflow files)} \subset \textrm{(CNAP workflow files)}
    $$

    Therefore, the WDL process can be shared without dependence on CNAP-specific requirements.

    
Together, the use of the git commit identifier along with the digests of the constitutive Docker containers provides the ability to *exactly* recover both the process and the computing environment necessary to recapitulate any analysis process.  All of this is handled by default, without any special care needed to ensure that everything is synced.

