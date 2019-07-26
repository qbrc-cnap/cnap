workflow Main {
    String z
    String other

    call sleep {
        input:
            z = z
    }

    output {
        File output = sleep.my_output
    }

    meta {
        workflow_title : "Dummy workflow"
        workflow_short_description : "For testing..."
        workflow_long_description : "For testing"
    }
}

task sleep {

    String z
    Int disk_size = 10
    command {
        echo "start"
        echo ${z} >> "something.txt"
        echo "stop"
    }

    output {
         File my_output = "something.txt"        
    }

    runtime {
        docker: "docker.io/blawney/basic_debian:v0.1"
        cpu: 2
        memory: "2 G"
        disks: "local-disk " + disk_size + " HDD"
        preemptible: 0
    }
}
