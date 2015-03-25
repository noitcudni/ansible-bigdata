package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"strings"
)

type host struct {
	ipAddr   string
	intrfce  string
	vlan     string
	function string
}

func parse(filepath string) map[string][]host {
	fh, err := os.Open(filepath)
	if err != nil {
		fmt.Println("Error: Can't open", filepath)
		return nil
	}
	defer fh.Close()

	r := make(map[string][]host)
	scanner := bufio.NewScanner(fh)
	for scanner.Scan() {
		line := scanner.Text()
		lst := strings.Split(line, ",")

		ip := lst[0]
		device := lst[2]
		intrfce := lst[3]
		vlan := lst[4]
		function := lst[5]

		if device == "DHCP Pool for IPMI" {
			// skip everything after this
			// We don't care about ip range range /mask.
			break
		}

		if ip == "IP Address" {
			// skip
			continue
		} else if len(device) > 0 && len(function) > 0 {
			_, ok := r[function]
			if ok == false {
				r[function] = make([]host, 0, 5)
			}
			r[function] = append(r[function], host{
				ip,
				intrfce,
				vlan,
				function,
			})
		}
	} // for

	return r
}

func write_out_inventory(function_host_map *map[string][]host) {
	f, err := os.Create("inventory")
	if err != nil {
		fmt.Println("Error: Can't create file", "inventory")
		return
	}
	defer f.Close()

	w := bufio.NewWriter(f)
	for host_grp, host_arry := range *function_host_map {
		fmt.Fprintln(w, fmt.Sprintf("[%s]", host_grp))

		for _, host := range host_arry {
			fmt.Fprintln(w, fmt.Sprintf("%s interface=%s", host.ipAddr, host.intrfce))
		}
		fmt.Fprintln(w, "") // newline
	}

	w.Flush()
}

func main() {
	var filepath string
	flag.StringVar(&filepath, "filepath", "You must enter a proper filepath", "Usage: the path of the layout csv file")
	flag.Parse()

	fmt.Println("Parsing:", filepath)
	parsed_d := parse(filepath)
	//fmt.Println(parsed_d)
	write_out_inventory(&parsed_d)
}
