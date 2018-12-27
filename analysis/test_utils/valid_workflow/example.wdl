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

    meta {
        workflow_title : "Concatenation flow"
        workflow_short_description : "For concatenating..."
        workflow_long_description : "Use this workflow for concatenating a number of files into a single file."

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
