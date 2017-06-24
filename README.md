# Python Implementation of the EVM

## Introducing Py-EVM
Py-EVM is a new implementation of the Ethereum Virtual Machine written in python. It is currently in active development but is quickly progressing through the test suite provided by ethereum/tests. I have Vitalik, and the existing PyEthereum code to thank for the quick progress I’ve made as many design decisions were inspired, or even directly ported from the PyEthereum codebase.
Py-EVM aims to eventually become the defacto python implementation of the EVM, enabling a wide array of use cases for both public and private chains. Development will focus on creating an EVM with a well defined API, friendly and easy to digest documentation which can be run as a fully functional mainnet node.

### Step 1: Alpha Release
The plan is to begin with an MVP, alpha-level release that is suitable for testing purposes. We’ll be looking for early adopters to provide feedback on our architecture and API choices as well as general feedback and bug finding.

Blog post:
https://medium.com/@pipermerriam/py-evm-part-1-origins-25d9ad390b

Ethnews:
https://www.ethnews.com/piper-merriam-wants-to-rebuild-pyethereum-introduces-py-evm?platform=hootsuite

Reddit discussion:
https://www.reddit.com/r/ethereum/comments/6igel2/pyevm_part_1_origins/

Join the chat:
https://gitter.im/pipermerriam/py-evm