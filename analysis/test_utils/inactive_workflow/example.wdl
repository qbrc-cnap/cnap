workflow TestWorkflow {
    
    Array[File] inputs
    String outputFilename

    call concat{
        input: myfiles=inputs,
            outFilename=outputFilename
    }

    output {
        File outFile = concat.fout
    }
}

task concat {
    Array[File] myfiles
    String outFilename

    command{
        cat ${sep=" " myfiles} > ${outFilename}
    }  

    output {
        File fout = "${outFilename}"
    }

}
