import "align.wdl" as align
import "quant.wdl" as quant
import "merge.wdl" as merge

workflow MyTestWorkflow {
    Array[String] sampleNames
    Array[Array[File]] inputs
    String genome_choice
    String outputFilename

    Array[Pair[String, Array[File]]] ABC = zip(sampleNames, inputs)

    scatter (i in ABC) {
        call align.AlignTask as AT{
            input: sampleName=i.left,
                fq1=i.right[0],
                fq2=i.right[1],
                genome=genome_choice
        }
        call quant.QuantTask as QT{
            input: genome=genome_choice,
                sampleName=i.left,
                bam=AT.bam_out,
                bai=AT.bai_out
        }
    }

    call merge.MergeTask as MT{
        input: count_files=QT.count_out,
            fname=outputFilename
    }

    output {
        File mergedFile = MT.mergedCounts
    }
}
