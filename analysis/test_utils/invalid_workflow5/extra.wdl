task junkTask {
    Array[File] myfiles
    String outFilename

    command{
        cat ${sep=" " myfiles} > ${outFilename}
    }  

    output {
        File fout = "${outFilename}"
    }

}
