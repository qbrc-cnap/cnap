task AlignTask {

    File fq1
    File fq2
    String genome
    String sampleName

    runtime {
        docker: "blawney/align_w_args:v1.0"
    }

    command {
        python /opt/software/align.py \
            -g ${genome} \
            -fq1 ${fq1} \
            -fq2 ${fq2}
    }

    output {
        File bam_out = "${sampleName}.bam"
        File bai_out = "${sampleName}.bai"
    }
}
