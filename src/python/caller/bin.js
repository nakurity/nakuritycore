// call command
const fs = require("fs")
const path = require("path")

const callers = fs.readFileSync(path.resolve(__dirname, "calllists.txt")).split("\n");

function is_call_listed(caller_name) {
  if (!caller_name) return Error("Caller name undefined! function is_call_listed")
  if (callers.includes(caller_name)) return true;
  return false;
}

function auggie() {
  const auggie = process.argv

  if (callers.include(auggie)
}

function main() {
  const args = process.args
}
