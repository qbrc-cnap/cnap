task QuantTask {

    File bam
    File bai
    String genome
    String sampleName

    runtime {
        docker: "blawney/quant:v1.2"
    }

    command {
        python /opt/software/quant.py \
            -s count \
            -g ${genome} \
            -bam ${bam} \
            -bai ${bai}
    }

    output {
        File count_out = "${sampleName}.count"
    }
}
