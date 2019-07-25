The CNAP contribution model follows the standard fork-branch model on the devel branch. Contributions are submitted as pull requets (PRs).

fork the cnap repo to your github

clone the forked repo to your computer

add a new remote typically called ‘upstream’ that points to the source of netZoo

git remote add upstream https://github.com/qbrc-cnap/cnap.git

switch to the devel branch, because your PR will target the devel branch

git checkout devel

create a new branch called new-feature off of the devel branch

git checkout -b new-feature

make the changes/additions to CNAP

add your changess

git add .

commit your changes

git commit -m 'commit message'

push your PR

git push origin new-feature

go the CNAP website https://github.com/qbrc-cnap/cnap

create a pull request through the pop-up

make sure to change the target to devel branch not the master branch

the PR will go through automatic tests and it will be accepted by the moderators if it passes the tests

if the PR does not pass the test, further changes need to be made (step 7-9)

once the PR integrated in the devel branch, you can delete new-feature, switch back to devel branch and update it with the new branch through

git checkout devel

git fetch upstream

git merge usptream/devel

you can do the same for the master branch to update it.
